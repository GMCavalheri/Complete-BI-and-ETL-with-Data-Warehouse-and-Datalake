"""
load.py
=======
The "processed (lake) -> warehouse" stage. This is the file that actually
answers "how do you integrate a data lake with a data warehouse":

    1. DuckDB reads the cleaned Parquet files straight off disk and runs
       a SQL JOIN between orders and products — this is the lake's
       analytical query engine doing real work (computing `revenue`)
       *before* anything touches Postgres.
    2. The result of that DuckDB query is fetched as a PyArrow Table
       (`.arrow()`). This is the interchange step: DuckDB, Polars (used
       in ingest.py) and PyArrow all speak the same in-memory Arrow
       format, so no serialization/deserialization dance is needed
       between "lake tools" — the same Arrow buffers are just handed
       from one library to the next.
    3. psycopg2 loads that data into PostgreSQL — dimensions first
       (with UPSERT, since dimensions can legitimately be re-loaded and
       updated), then the fact table (with a full-refresh TRUNCATE +
       INSERT, the simplest correct strategy for a fact table with no
       natural unique key at this grain).

Load order matters: dimensions must exist before the fact table, because
fact_sales rows reference dimension surrogate keys via foreign keys.

Run (from the project root, with PostgreSQL reachable per config.yaml):
    python -m warehouse.load
"""

import os
from datetime import date, timedelta

import duckdb
import psycopg2
import psycopg2.extras
import pyarrow.parquet as pq
import yaml

from src.logger import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def resolve_env_placeholder(value: str):
    """
    config.yaml uses `${VAR_NAME:default}` for anything that should be
    overridable via environment variable (host, password) without
    editing the file — e.g. Docker Compose injects real values this way.
    Plain values (like the port, which rarely changes) pass through
    unchanged.
    """
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        inner = value[2:-1]
        var_name, _, default = inner.partition(":")
        return os.environ.get(var_name, default)
    return value


def get_connection(cfg: dict):
    db_cfg = cfg["database"]
    conn = psycopg2.connect(
        host=resolve_env_placeholder(db_cfg["host"]),
        port=db_cfg["port"],
        dbname=db_cfg["name"],
        user=db_cfg["user"],
        password=resolve_env_placeholder(db_cfg["password"]),
    )
    logger.info(f"Connected to Postgres at {resolve_env_placeholder(db_cfg['host'])}:{db_cfg['port']}/{db_cfg['name']}")
    return conn


# -----------------------------------------------------------------------------
# DIM_DATE — built programmatically, not read from any file. Every date in
# the configured range gets a row, whether or not an order happened that
# day, so time-series queries (e.g. "revenue by day, including zero-order
# days") never have gaps.
# -----------------------------------------------------------------------------
def load_dim_date(conn, start_date: date, end_date: date) -> int:
    rows = []
    current = start_date
    while current <= end_date:
        date_key = int(current.strftime("%Y%m%d"))
        rows.append((
            date_key,
            current,
            current.day,
            current.month,
            MONTH_NAMES[current.month - 1],
            (current.month - 1) // 3 + 1,
            current.year,
            current.weekday(),  # 0=Monday .. 6=Sunday
            DAY_NAMES[current.weekday()],
            current.weekday() >= 5,
        ))
        current += timedelta(days=1)

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO dim_date
                (date_key, full_date, day, month, month_name, quarter, year, day_of_week, day_name, is_weekend)
            VALUES %s
            ON CONFLICT (date_key) DO NOTHING
            """,
            rows,
        )
    conn.commit()
    logger.info(f"[dim_date] upserted {len(rows)} calendar days ({start_date} to {end_date})")
    return len(rows)


# -----------------------------------------------------------------------------
# Dimension loaders — read straight from the cleaned Parquet files via
# PyArrow, then UPSERT into Postgres keyed on the natural id. UPSERT
# (rather than plain INSERT) means re-running the pipeline after new/
# updated source data is safe — this is "Slowly Changing Dimension Type 1"
# behavior: the latest attributes overwrite the old ones.
# -----------------------------------------------------------------------------
def load_dim_customers(conn, processed_dir: str) -> int:
    table = pq.read_table(os.path.join(processed_dir, "customers.parquet"))
    rows = list(zip(
        table["customer_id"].to_pylist(),
        table["first_name"].to_pylist(),
        table["last_name"].to_pylist(),
        table["email"].to_pylist(),
        table["signup_date"].to_pylist(),
        table["city"].to_pylist(),
        table["country"].to_pylist(),
    ))
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO dim_customer (customer_id, first_name, last_name, email, signup_date, city, country)
            VALUES %s
            ON CONFLICT (customer_id) DO UPDATE SET
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                email = EXCLUDED.email,
                signup_date = EXCLUDED.signup_date,
                city = EXCLUDED.city,
                country = EXCLUDED.country
            """,
            rows,
        )
    conn.commit()
    logger.info(f"[dim_customer] upserted {len(rows)} rows")
    return len(rows)


def load_dim_products(conn, processed_dir: str) -> int:
    table = pq.read_table(os.path.join(processed_dir, "products.parquet"))
    rows = list(zip(
        table["product_id"].to_pylist(),
        table["product_name"].to_pylist(),
        table["category"].to_pylist(),
        table["unit_price"].to_pylist(),
    ))
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO dim_product (product_id, product_name, category, unit_price)
            VALUES %s
            ON CONFLICT (product_id) DO UPDATE SET
                product_name = EXCLUDED.product_name,
                category = EXCLUDED.category,
                unit_price = EXCLUDED.unit_price
            """,
            rows,
        )
    conn.commit()
    logger.info(f"[dim_product] upserted {len(rows)} rows")
    return len(rows)


def load_dim_stores(conn, processed_dir: str) -> int:
    table = pq.read_table(os.path.join(processed_dir, "stores.parquet"))
    rows = list(zip(
        table["store_id"].to_pylist(),
        table["store_name"].to_pylist(),
        table["city"].to_pylist(),
        table["country"].to_pylist(),
    ))
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO dim_store (store_id, store_name, city, country)
            VALUES %s
            ON CONFLICT (store_id) DO UPDATE SET
                store_name = EXCLUDED.store_name,
                city = EXCLUDED.city,
                country = EXCLUDED.country
            """,
            rows,
        )
    conn.commit()
    logger.info(f"[dim_store] upserted {len(rows)} rows")
    return len(rows)


# -----------------------------------------------------------------------------
# Fact table build — this is the actual "lake -> warehouse integration"
# step: DuckDB joins orders to products directly on the Parquet files
# (no Postgres involved yet) to compute unit_price + revenue per line
# item, and hands the result back as a PyArrow Table.
# -----------------------------------------------------------------------------
def build_fact_rows_with_duckdb(processed_dir: str):
    orders_path = os.path.join(processed_dir, "orders.parquet")
    products_path = os.path.join(processed_dir, "products.parquet")

    con = duckdb.connect()
    arrow_table = con.execute(
        f"""
        SELECT
            o.order_id,
            o.customer_id,
            o.product_id,
            o.store_id,
            o.order_date,
            o.channel,
            o.quantity,
            p.unit_price,
            ROUND(o.quantity * p.unit_price, 2) AS revenue
        FROM read_parquet('{orders_path}') o
        JOIN read_parquet('{products_path}') p
            ON o.product_id = p.product_id
        """
    ).to_arrow_table()
    con.close()

    logger.info(f"[fact_sales] DuckDB joined orders x products -> {arrow_table.num_rows} rows (Arrow interchange)")
    return arrow_table


def fetch_key_mapping(conn, table: str, natural_col: str, key_col: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {natural_col}, {key_col} FROM {table}")
        return dict(cur.fetchall())


def load_fact_sales(conn, fact_table, batch_size: int) -> int:
    customer_map = fetch_key_mapping(conn, "dim_customer", "customer_id", "customer_key")
    product_map = fetch_key_mapping(conn, "dim_product", "product_id", "product_key")
    store_map = fetch_key_mapping(conn, "dim_store", "store_id", "store_key")

    order_ids = fact_table["order_id"].to_pylist()
    customer_ids = fact_table["customer_id"].to_pylist()
    product_ids = fact_table["product_id"].to_pylist()
    store_ids = fact_table["store_id"].to_pylist()
    order_dates = fact_table["order_date"].to_pylist()
    channels = fact_table["channel"].to_pylist()
    quantities = fact_table["quantity"].to_pylist()
    unit_prices = fact_table["unit_price"].to_pylist()
    revenues = fact_table["revenue"].to_pylist()

    rows = []
    skipped = 0
    for i in range(fact_table.num_rows):
        customer_key = customer_map.get(customer_ids[i])
        product_key = product_map.get(product_ids[i])
        store_key = store_map.get(store_ids[i])
        if customer_key is None or product_key is None or store_key is None:
            # Shouldn't happen after ingest.py's referential integrity
            # check, but a load step should never trust an upstream
            # step blindly — skip and count rather than crash.
            skipped += 1
            continue

        date_key = int(order_dates[i].strftime("%Y%m%d"))
        rows.append((
            order_ids[i], customer_key, product_key, store_key, date_key,
            channels[i], quantities[i], unit_prices[i], revenues[i],
        ))

    if skipped:
        logger.warning(f"[fact_sales] skipped {skipped} rows with no matching dimension key")

    with conn.cursor() as cur:
        # Full-refresh strategy: this project reloads the whole fact
        # table each run rather than doing incremental upserts. Simpler
        # and correct for a portfolio-scale dataset; a production
        # pipeline processing daily deltas would instead insert only
        # new order_ids. Worth calling out as a known simplification.
        cur.execute("TRUNCATE TABLE fact_sales RESTART IDENTITY")
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO fact_sales
                (order_id, customer_key, product_key, store_key, date_key, channel, quantity, unit_price, revenue)
            VALUES %s
            """,
            rows,
            page_size=batch_size,
        )
    conn.commit()
    logger.info(f"[fact_sales] inserted {len(rows)} rows (batch_size={batch_size})")
    return len(rows)


def main():
    cfg = load_config()
    processed_dir = os.path.join(PROJECT_ROOT, cfg["paths"]["processed_data"])
    batch_size = cfg["pipeline"]["batch_size"]

    logger.info("Starting warehouse load (processed lake -> Postgres)")

    conn = get_connection(cfg)
    try:
        start_date = date.fromisoformat(cfg["data_generation"]["start_date"])
        end_date = date.fromisoformat(cfg["data_generation"]["end_date"])
        load_dim_date(conn, start_date, end_date)

        load_dim_customers(conn, processed_dir)
        load_dim_products(conn, processed_dir)
        load_dim_stores(conn, processed_dir)

        fact_table = build_fact_rows_with_duckdb(processed_dir)
        load_fact_sales(conn, fact_table, batch_size)

        logger.info("Warehouse load complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
