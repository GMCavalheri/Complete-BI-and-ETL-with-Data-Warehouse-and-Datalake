"""
generate_data.py
=================
Generates a synthetic e-commerce dataset and writes it to `data/raw/` as CSV
files — simulating what a "raw landing zone" in a real data lake looks like:
files dumped as-is from some upstream source, with all the imperfections
real data has.

Why generate data instead of downloading a public dataset?
------------------------------------------------------------
1. Full control over volume (so the pipeline is fast to demo, but the SQL
   queries are still meaningful over tens of thousands of rows).
2. We can deliberately inject realistic data-quality issues (duplicate
   emails, inconsistent date formats, nulls, bad values) — this gives the
   later ingestion/cleaning step (Polars, in `lake/ingest.py`) real work
   to do, instead of just copying already-clean data around.
3. Fully reproducible: a fixed random seed means anyone who clones the
   repo and runs this script gets the exact same dataset.

Output (all under data/raw/):
    customers.csv
    products.csv
    stores.csv
    orders.csv   <- the "fact" data: one row per line item in an order

Run:
    python lake/generate_data.py
"""

import csv
import os
import random
from datetime import datetime, timedelta

import yaml
from faker import Faker

from src.logger import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")


def load_config() -> dict:
    """Load config.yaml. Environment-variable placeholders (${VAR:default})
    are only relevant to the database section, so we don't need to resolve
    them here — this script only cares about `data_generation` and `paths`.
    """
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    logger.info(f"Loaded config from {CONFIG_PATH}")
    return config


def random_date_between(start: datetime, end: datetime) -> datetime:
    delta = end - start
    random_days = random.randint(0, delta.days)
    return start + timedelta(days=random_days)


def format_date_messily(date: datetime, mixed_format_rate: float) -> str:
    """
    Most real-world raw exports are NOT consistently ISO-formatted —
    especially when data comes from multiple upstream systems (e.g. one
    store's POS system exports dates differently than the e-commerce
    platform). We simulate that here so the ingestion step has to
    normalize dates, a very common real-world data-cleaning task.
    """
    if random.random() < mixed_format_rate:
        fmt = random.choice(["%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d"])
    else:
        fmt = "%Y-%m-%d"  # ISO 8601 — the "correct" format
    return date.strftime(fmt)


def generate_customers(fake: Faker, cfg: dict) -> list[dict]:
    n = cfg["data_generation"]["num_customers"]
    dup_rate = cfg["data_generation"]["messiness"]["duplicate_email_rate"]
    null_city_rate = cfg["data_generation"]["messiness"]["null_city_rate"]

    customers = []
    used_emails = []

    for customer_id in range(1, n + 1):
        # Occasionally reuse a previous customer's email, simulating a
        # duplicate/guest-checkout account — a classic real-world data
        # quality problem for a "customer" dimension.
        if used_emails and random.random() < dup_rate:
            email = random.choice(used_emails)
        else:
            email = fake.unique.email()
            used_emails.append(email)

        city = None if random.random() < null_city_rate else fake.city()

        customers.append(
            {
                "customer_id": customer_id,
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "email": email,
                "signup_date": fake.date_between(start_date="-3y", end_date="today").isoformat(),
                "city": city,
                "country": fake.country(),
            }
        )

    logger.info(f"Generated {len(customers)} customer records ({len(used_emails)} unique emails)")
    return customers


CATEGORIES = [
    "Electronics", "Home & Kitchen", "Books", "Clothing", "Sports & Outdoors",
    "Toys & Games", "Beauty", "Grocery", "Office Supplies", "Pet Supplies",
]


def generate_products(fake: Faker, cfg: dict) -> list[dict]:
    n = cfg["data_generation"]["num_products"]
    products = []
    for product_id in range(1, n + 1):
        products.append(
            {
                "product_id": product_id,
                "product_name": fake.catch_phrase(),
                "category": random.choice(CATEGORIES),
                "unit_price": round(random.uniform(3.99, 499.99), 2),
            }
        )
    logger.info(f"Generated {len(products)} product records")
    return products


def generate_stores(fake: Faker, cfg: dict) -> list[dict]:
    n = cfg["data_generation"]["num_stores"]
    stores = []
    for store_id in range(1, n + 1):
        stores.append(
            {
                "store_id": store_id,
                "store_name": f"{fake.city()} Store #{store_id}",
                "city": fake.city(),
                "country": fake.country(),
            }
        )
    logger.info(f"Generated {len(stores)} store records")
    return stores


CHANNELS = ["online", "in_store", "mobile_app", "marketplace"]


def generate_orders(cfg: dict, num_customers: int, num_products: int, num_stores: int) -> list[dict]:
    gen_cfg = cfg["data_generation"]
    n = gen_cfg["num_orders"]
    mess = gen_cfg["messiness"]

    start_date = datetime.fromisoformat(gen_cfg["start_date"])
    end_date = datetime.fromisoformat(gen_cfg["end_date"])

    orders = []
    for order_id in range(1, n + 1):
        order_date = random_date_between(start_date, end_date)

        # Inject bad quantities: null or negative (e.g. a return logged
        # incorrectly, or a failed form validation upstream).
        roll = random.random()
        if roll < mess["null_quantity_rate"]:
            quantity = None
        elif roll < mess["null_quantity_rate"] + mess["negative_quantity_rate"]:
            quantity = -random.randint(1, 5)
        else:
            quantity = random.randint(1, 10)

        orders.append(
            {
                "order_id": order_id,
                "customer_id": random.randint(1, num_customers),
                "product_id": random.randint(1, num_products),
                "store_id": random.randint(1, num_stores),
                "order_date": format_date_messily(order_date, mess["mixed_date_format_rate"]),
                "quantity": quantity,
                "channel": random.choice(CHANNELS),
            }
        )

    logger.info(f"Generated {len(orders)} order records")
    return orders


def write_csv(rows: list[dict], filepath: str) -> None:
    if not rows:
        logger.warning(f"No rows to write for {filepath}")
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"Wrote {len(rows)} rows -> {filepath}")


def main():
    cfg = load_config()
    seed = cfg["data_generation"]["seed"]
    random.seed(seed)
    fake = Faker()
    Faker.seed(seed)

    logger.info(f"Starting data generation with seed={seed}")

    raw_dir = os.path.join(PROJECT_ROOT, cfg["paths"]["raw_data"])

    customers = generate_customers(fake, cfg)
    products = generate_products(fake, cfg)
    stores = generate_stores(fake, cfg)
    orders = generate_orders(
        cfg,
        num_customers=len(customers),
        num_products=len(products),
        num_stores=len(stores),
    )

    write_csv(customers, os.path.join(raw_dir, "customers.csv"))
    write_csv(products, os.path.join(raw_dir, "products.csv"))
    write_csv(stores, os.path.join(raw_dir, "stores.csv"))
    write_csv(orders, os.path.join(raw_dir, "orders.csv"))

    logger.info("Data generation complete.")


if __name__ == "__main__":
    main()
