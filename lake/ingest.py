"""
ingest.py
=========
The "raw -> processed" stage of the data lake. Reads the messy CSVs from
`data/raw/` (see `lake/generate_data.py`), cleans them with Polars, and
writes cleaned Parquet files to `data/processed/`.

Why Polars here (and not pandas)?
----------------------------------
Polars is built on Apache Arrow (the same in-memory format PyArrow uses),
is significantly faster than pandas on this kind of row-wise
transformation, and has a stricter, more predictable type system — which
matters when the whole point of this step is "enforce a strict shape on
messy data". Writing `df.write_parquet(...)` from a Polars DataFrame
produces a real Arrow-backed Parquet file, the same format DuckDB queries
directly and PyArrow reads in `warehouse/load.py` — this is what "lake"
tools sharing the Arrow format in memory/on disk actually looks like in
practice, not just three unrelated libraries.

Why Parquet instead of just re-writing CSV?
---------------------------------------------
Parquet is columnar, compressed, and carries a schema (types are stored
in the file, unlike CSV where everything is a string until parsed). This
is what makes DuckDB queries and warehouse loads fast and correct instead
of re-guessing types on every read.

Cleaning rules applied (this is the "silver layer" of a lake):
- customers: trim whitespace, lowercase/trim emails, keep nulls in
  `city` as real nulls (not the string "None"), log duplicate emails as a
  data-quality metric (customer_id remains the real identity, so we don't
  drop these rows).
- products / stores: trim whitespace on text columns.
- orders: normalize 4 different raw date formats into one ISO date column;
  reject (quarantine) rows with null or negative quantity instead of
  silently keeping or silently dropping them — this is the audit trail a
  real pipeline needs.

Run (from the project root):
    python -m lake.ingest
"""

import os
from datetime import datetime

import polars as pl
import yaml

from src.logger import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")

# The exact set of formats generate_data.py can produce. Kept explicit
# (rather than a "guess the format" library) so parsing behavior is
# predictable and testable.
KNOWN_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d"]


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def parse_messy_date(value: str) -> "datetime.date | None":
    """
    Try each known raw date format in turn. Returns None (rather than
    raising) on failure, so a single bad value doesn't crash the whole
    pipeline — it gets counted and reported instead, via the null-check
    that follows this function's use in `clean_orders`.
    """
    if value is None:
        return None
    for fmt in KNOWN_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def clean_customers(raw_dir: str) -> pl.DataFrame:
    df = pl.read_csv(os.path.join(raw_dir, "customers.csv"))
    n_in = df.height

    df = df.with_columns(
        pl.col("first_name").str.strip_chars(),
        pl.col("last_name").str.strip_chars(),
        pl.col("email").str.strip_chars().str.to_lowercase(),
        pl.col("city").str.strip_chars(),
        pl.col("country").str.strip_chars(),
        pl.col("signup_date").str.to_date("%Y-%m-%d", strict=False),
    )

    null_cities = df.filter(pl.col("city").is_null()).height
    duplicate_emails = n_in - df.select("email").unique().height

    logger.info(f"[customers] read {n_in} rows")
    logger.info(f"[customers] {null_cities} rows with null city (kept as-is, dimension allows null)")
    if duplicate_emails > 0:
        logger.warning(
            f"[customers] {duplicate_emails} rows share an email with another customer_id "
            f"(kept — customer_id is the real identity, this is just noted for visibility)"
        )

    return df


def clean_products(raw_dir: str) -> pl.DataFrame:
    df = pl.read_csv(os.path.join(raw_dir, "products.csv"))
    df = df.with_columns(
        pl.col("product_name").str.strip_chars(),
        pl.col("category").str.strip_chars(),
    )
    logger.info(f"[products] read {df.height} rows, no rejections (source is already well-formed)")
    return df


def clean_stores(raw_dir: str) -> pl.DataFrame:
    df = pl.read_csv(os.path.join(raw_dir, "stores.csv"))
    df = df.with_columns(
        pl.col("store_name").str.strip_chars(),
        pl.col("city").str.strip_chars(),
        pl.col("country").str.strip_chars(),
    )
    logger.info(f"[stores] read {df.height} rows, no rejections (source is already well-formed)")
    return df


def clean_orders(raw_dir: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Returns (clean_df, rejected_df). Rejected rows are kept — with a
    reason — rather than silently dropped, so the ingestion has an
    auditable trail of exactly what data quality problems existed and
    how many rows they affected. This is standard practice in real
    pipelines: never silently discard data.
    """
    df = pl.read_csv(
        os.path.join(raw_dir, "orders.csv"),
        schema_overrides={"quantity": pl.Int64},  # allow nulls to parse instead of erroring
    )
    n_in = df.height

    # Normalize the mixed date formats into one real pl.Date column.
    df = df.with_columns(
        pl.col("order_date")
        .map_elements(parse_messy_date, return_dtype=pl.Date)
        .alias("order_date")
    )

    unparseable_dates = df.filter(pl.col("order_date").is_null()).height
    if unparseable_dates > 0:
        logger.warning(f"[orders] {unparseable_dates} rows had a date in none of the known formats")

    # Split into clean vs. rejected based on quantity validity.
    # (Unparseable dates would also show up here since we require both
    # a valid date AND a valid quantity for a row to be usable downstream.)
    is_valid = (pl.col("quantity").is_not_null()) & (pl.col("quantity") > 0) & (pl.col("order_date").is_not_null())

    clean_df = df.filter(is_valid)

    rejected_df = df.filter(~is_valid).with_columns(
        pl.when(pl.col("order_date").is_null())
        .then(pl.lit("unparseable_date"))
        .when(pl.col("quantity").is_null())
        .then(pl.lit("null_quantity"))
        .when(pl.col("quantity") <= 0)
        .then(pl.lit("non_positive_quantity"))
        .otherwise(pl.lit("unknown"))
        .alias("rejection_reason")
    )

    n_clean = clean_df.height
    n_rejected = rejected_df.height
    reject_rate = (n_rejected / n_in * 100) if n_in else 0

    logger.info(f"[orders] read {n_in} rows")
    logger.info(f"[orders] {n_clean} rows passed validation -> processed")
    logger.warning(f"[orders] {n_rejected} rows quarantined ({reject_rate:.2f}%) -> data/processed/quarantine/")

    return clean_df, rejected_df


def check_referential_integrity(orders: pl.DataFrame, customers: pl.DataFrame,
                                  products: pl.DataFrame, stores: pl.DataFrame) -> pl.DataFrame:
    """
    Defensive check: confirm every customer_id/product_id/store_id in the
    cleaned orders actually exists in its cleaned dimension. With our own
    synthetic generator this should always pass, but a real pipeline
    ingesting from an actual upstream source cannot assume that — orphan
    foreign keys (an order for a customer_id that was deleted, for
    example) are extremely common in practice. Orphans are quarantined
    the same way invalid quantities are, not silently loaded.
    """
    valid_customer_ids = set(customers["customer_id"].to_list())
    valid_product_ids = set(products["product_id"].to_list())
    valid_store_ids = set(stores["store_id"].to_list())

    is_valid_fk = (
        pl.col("customer_id").is_in(valid_customer_ids)
        & pl.col("product_id").is_in(valid_product_ids)
        & pl.col("store_id").is_in(valid_store_ids)
    )

    orphans = orders.filter(~is_valid_fk)
    if orphans.height > 0:
        logger.warning(f"[orders] {orphans.height} rows reference a customer/product/store_id not found in dimensions — quarantined")
    else:
        logger.info("[orders] referential integrity check passed: all customer/product/store_id values exist in their dimension")

    return orders.filter(is_valid_fk), orphans.with_columns(pl.lit("orphan_foreign_key").alias("rejection_reason"))


def write_parquet(df: pl.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.write_parquet(path)
    logger.info(f"Wrote {df.height} rows -> {path}")


def main():
    cfg = load_config()
    raw_dir = os.path.join(PROJECT_ROOT, cfg["paths"]["raw_data"])
    processed_dir = os.path.join(PROJECT_ROOT, cfg["paths"]["processed_data"])

    logger.info("Starting lake ingestion (raw -> processed)")

    customers = clean_customers(raw_dir)
    products = clean_products(raw_dir)
    stores = clean_stores(raw_dir)
    orders_clean, orders_rejected_quality = clean_orders(raw_dir)

    orders_clean, orders_rejected_fk = check_referential_integrity(orders_clean, customers, products, stores)

    all_rejected = pl.concat([orders_rejected_quality, orders_rejected_fk], how="diagonal")

    write_parquet(customers, os.path.join(processed_dir, "customers.parquet"))
    write_parquet(products, os.path.join(processed_dir, "products.parquet"))
    write_parquet(stores, os.path.join(processed_dir, "stores.parquet"))
    write_parquet(orders_clean, os.path.join(processed_dir, "orders.parquet"))

    if all_rejected.height > 0:
        write_parquet(all_rejected, os.path.join(processed_dir, "quarantine", "orders_rejected.parquet"))

    logger.info(
        f"Ingestion complete. orders: {orders_clean.height} clean, "
        f"{all_rejected.height} quarantined out of {orders_clean.height + all_rejected.height} total"
    )


if __name__ == "__main__":
    main()
