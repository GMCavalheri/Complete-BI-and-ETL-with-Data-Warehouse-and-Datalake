# Data Warehouse ↔ Data Lake Integration

A portfolio project demonstrating how a **Data Lake** (raw file storage + fast
analytical tooling) and a **Data Warehouse** (structured, query-optimized
relational storage) integrate in a real pipeline — from messy raw data, to
cleaned lake files, to a modeled star schema ready for analysis.

Built as my second portfolio project to showcase SQL (basic → advanced) and
practical data engineering: ETL design, data quality handling, and
containerized, config-driven infrastructure.

---

## What this project shows

- A working **ETL pipeline**: generate → clean → load, each stage a separate,
  testable script.
- **Real data-quality handling**: the raw data is deliberately messy
  (duplicate emails, inconsistent date formats, null/negative quantities),
  and the pipeline detects, cleans, and quarantines it — not just processes
  clean input.
- A proper **star schema** data warehouse in PostgreSQL, with 33 SQL queries
  spanning basic filtering through window functions and recursive CTEs.
- **Reproducible infrastructure**: one `docker compose up --build` runs the
  whole thing — database included — on any machine.

---

## Architecture

```
┌─────────────────────┐
│  lake/generate_data  │   Synthetic e-commerce data, seeded & reproducible,
│  (Faker)             │   with intentional data-quality issues injected.
└──────────┬───────────┘
           │ writes CSV
           ▼
   data/raw/*.csv                 <- the "landing zone"
           │
┌──────────▼───────────┐
│  lake/ingest          │   Cleans, validates, normalizes dates,
│  (Polars)             │   quarantines bad rows.
└──────────┬───────────┘
           │ writes Parquet
           ▼
   data/processed/*.parquet       <- the "cleaned" lake layer
           │
┌──────────▼───────────┐
│  warehouse/load        │   DuckDB joins orders × products (computes
│  (DuckDB + PyArrow)    │   revenue) directly on the Parquet files.
│                         │   Result handed off as a PyArrow Table —
│                         │   the same Arrow format Polars wrote —
│                         │   no serialization in between.
└──────────┬─────────────┘
           │ psycopg2 batch upsert / insert
           ▼
   PostgreSQL — star schema
   dim_customer, dim_product, dim_store, dim_date, fact_sales
           │
           ▼
   warehouse/queries/*.sql        <- basic → window-function SQL showcase
```

**Why this shape?** A data lake is cheap, flexible raw/semi-structured
storage — good for landing data as-is and doing fast ad-hoc analytics
(DuckDB queries Parquet directly, no loading step). A data warehouse is
schema-enforced, relationally modeled, and optimized for repeatable
analytical queries. Real organizations use both: the lake absorbs whatever
arrives, the warehouse is the trusted, modeled layer BI tools and analysts
actually query. This project's `warehouse/load.py` is the bridge between
them.

---

## Tech stack

| Layer | Tool | Role |
|---|---|---|
| Data Lake | **Polars** | Fast, Arrow-backed DataFrame cleaning/transformation |
| Data Lake | **DuckDB** | SQL engine that queries Parquet files directly, no server |
| Data Lake | **PyArrow** | The in-memory columnar format Polars, DuckDB, and Parquet all share — the "interchange" layer |
| Data Warehouse | **PostgreSQL** | Relational database, star schema, source of truth for analysis |
| Data Warehouse | **SQL** | 33 queries, basic through window functions |
| Infra | **Docker / Docker Compose** | Reproducible environment, YAML-based configuration |
| Other | **Faker**, **PyYAML**, **psycopg2**, **pytest** | Synthetic data, config loading, DB driver, testing |

---

## Project structure

```
Complete-BI-and-ETL-with-Data-Warehouse-and-Datalake/
├── docker-compose.yml         # postgres + pipeline services
├── Dockerfile                 # pipeline app image
├── config/
│   └── config.yaml            # every path/DB-setting/param — nothing hardcoded
├── lake/
│   ├── generate_data.py       # synthetic e-commerce data generator
│   └── ingest.py              # Polars cleaning: raw -> processed
├── warehouse/
│   ├── schema.sql             # star schema DDL
│   ├── load.py                # DuckDB join -> PyArrow -> Postgres
│   └── queries/
│       ├── 01_basic.sql
│       ├── 02_intermediate.sql
│       ├── 03_advanced.sql
│       └── 04_window_functions.sql
├── src/
│   └── logger.py              # shared logging config
├── scripts/
│   └── run_pipeline.sh        # generate -> ingest -> load, fail-fast
├── tests/
│   ├── test_ingest.py
│   └── test_load.py
├── data/                      # generated at runtime, gitignored
└── logs/                      # generated at runtime, gitignored
```

---

## The data

Since I couldn't find a public dataset that fit what I wanted to demonstrate,
I generate a synthetic **e-commerce** dataset with [Faker](https://faker.readthedocs.io/):

- 3,000 customers, 300 products (10 categories), 25 stores, 60,000 orders
- Seeded (`config.yaml: data_generation.seed`) — anyone who clones this repo
  and runs the generator gets the *exact same* dataset
- **Deliberately messy**, to give the cleaning step real work to do:
  - ~2–3% of customers share an email with another `customer_id`
  - ~5% of customers have a null `city`
  - ~30% of order dates use a non-ISO format (`MM/DD/YYYY`, `DD-Mon-YYYY`, `YYYY/MM/DD`)
  - ~1.5% of orders have a null or negative `quantity`

`lake/ingest.py` cleans this: normalizes emails/whitespace, parses every
known date format into one consistent type, and **quarantines** (not
silently drops) rows with an invalid quantity or an unrecognized date —
of the 60,000 generated orders, 59,024 pass validation and 976 are
quarantined to `data/processed/quarantine/orders_rejected.parquet` with a
`rejection_reason` column.

---

## The warehouse schema

A **star schema**: `fact_sales` (grain: one row per order line item) joined
to four dimensions — `dim_customer`, `dim_product`, `dim_store`, and a
programmatically-generated `dim_date` (every calendar day in range, so
time-series queries never have gaps). See `warehouse/schema.sql` for the
full DDL, including comments explaining each design choice (surrogate vs.
natural keys, indexing strategy, etc.).

---

## Getting started

### Option A — Docker (recommended)

```bash
git clone git@github.com:GMCavalheri/Complete-BI-and-ETL-with-Data-Warehouse-and-Datalake.git
cd Complete-BI-and-ETL-with-Data-Warehouse-and-Datalake
docker compose up --build
```

This will:
1. Start PostgreSQL and wait until it's actually ready to accept connections
   (a healthcheck, not just "container started")
2. Auto-apply `warehouse/schema.sql` on first boot
3. Run the full pipeline (`generate → ingest → load`) inside a second
   container
4. Exit with code 0 when done — your warehouse is loaded and ready to query

Then connect and explore. The `postgres` container has `warehouse/queries/`
mounted at `/queries`, so reference that in-container path (not the host
path) when using `exec`:

```bash
docker compose exec postgres psql -U dw_user -d dw_lake -f /queries/01_basic.sql
```

Alternatively, since `docker-compose.yml` publishes Postgres on
`localhost:5432`, you can skip `exec` entirely and connect from your host's
own `psql` client using the host-side path directly:

```bash
PGPASSWORD=dw_password psql -h localhost -U dw_user -d dw_lake -f warehouse/queries/01_basic.sql
```

**Note:** `schema.sql` only auto-applies the *first* time the Postgres
container initializes its data volume. If you edit the schema later, run
`docker compose down -v` first (this deletes the database volume) before
`docker compose up --build` again, or apply the change manually with `psql`.

### Option B — Local (no Docker)

Requires Python 3.12+ and a running PostgreSQL instance.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# create the database and apply the schema
psql -h localhost -U <your_user> -c "CREATE DATABASE dw_lake;"
psql -h localhost -U <your_user> -d dw_lake -f warehouse/schema.sql

# run each pipeline stage — note the -m flag, not a direct file path;
# this project uses `from src... / from lake...` imports that only
# resolve correctly when run as a module from the project root
python -m lake.generate_data
python -m lake.ingest
python -m warehouse.load
```

Adjust `config/config.yaml` (or set `POSTGRES_HOST` / `POSTGRES_PASSWORD`
environment variables) to match your local Postgres credentials.

---

## Running the SQL queries

```bash
psql -h localhost -U dw_user -d dw_lake -f warehouse/queries/01_basic.sql
```

Each file builds on the last:

| File | Covers |
|---|---|
| `01_basic.sql` | `SELECT`/`WHERE`/`ORDER BY`, aggregates, `GROUP BY`/`HAVING`, simple `JOIN`s |
| `02_intermediate.sql` | multi-table joins, `CASE`, scalar/`IN`/correlated subqueries, `COUNT(DISTINCT)`, `LEFT JOIN` anti-joins |
| `03_advanced.sql` | CTEs, a **recursive CTE** (generates its own date series), pivoting via `FILTER`, `UNION`/`INTERSECT`, self-joins |
| `04_window_functions.sql` | `RANK`/`ROW_NUMBER`/`DENSE_RANK`, top-N-per-group, running totals, moving averages, `LAG`/`LEAD`, `NTILE` customer segmentation, `FIRST_VALUE`/`LAST_VALUE` |

Every query is commented with what it answers and why that SQL feature is
the right tool for it — not just *what* the syntax does but *when* you'd
reach for it.

---

## Testing

```bash
pytest tests/ -v
```

21 unit tests covering the pure/deterministic logic: date-format parsing,
referential integrity checks, quantity validation rules, and config
placeholder resolution. Functions that require a live database connection
(the actual Postgres upserts) are intentionally **not** unit tested here —
that's an integration-testing concern, and mixing the two would make the
suite slow and environment-dependent. A natural next step would be adding
a docker-compose-backed integration test tier for those.

---

## Debugging notes / what I learned

A few real issues came up while building this, worth keeping for anyone
reading the commit history or asking about this project in an interview:

- **DuckDB API drift across versions.** `duckdb==1.1.3` (pinned in
  `requirements.txt`) doesn't have `.to_arrow_table()` — that method was
  added in a later release. The version-safe call is `.fetch_arrow_table()`.
  This surfaced specifically when running in Docker (which installs the
  exact pinned version) after testing locally against a newer ad-hoc
  install — a good reminder that pinned requirements exist precisely to
  catch this kind of drift, and that "works on my machine" isn't the same
  as "works in the container."
- **Quarantine over silent drop.** Early on it would have been simpler to
  just `.filter()` out bad rows in `ingest.py` and move on. Writing
  rejected rows to `data/processed/quarantine/` with a `rejection_reason`
  instead makes the pipeline auditable — you can always answer "why did I
  lose 976 orders" precisely.
- **`docker-entrypoint-initdb.d` only runs once.** The schema only
  auto-applies on a *fresh* Postgres volume — re-running
  `docker compose up` after an already-initialized volume won't pick up
  schema changes. Documented above so it doesn't look like a bug.

---

## Possible future improvements

- Incremental fact loads (currently a full `TRUNCATE` + reload) instead of
  processing only new `order_id`s since the last run
- Orchestration (Airflow/Dagster) instead of the current shell-script
  sequencing
- CI (GitHub Actions) running `pytest` and a docker-compose-based
  integration test on every push
- A small BI dashboard (e.g. Metabase, or a simple Streamlit app) on top of
  the warehouse

---

## License

MIT — feel free to use this as a reference for your own portfolio project.
