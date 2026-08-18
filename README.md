# Complete BI and ETL with Data Warehouse and Datalake

```
dw-lake-integration/
├── Dockerfile                        # pipeline app image (Python 3.12-slim)
├── docker-compose.yml                # postgres + pipeline services
├── .dockerignore
├── .env.example                      # POSTGRES_USER/PASSWORD/DB/PORT overrides
├── .gitignore
├── requirements.txt
│
├── config/
│   └── config.yaml                   # paths, DB settings, data-gen params — nothing hardcoded
│
├── data/
│   ├── raw/                          # generate_data.py output (gitignored)
│   │   ├── customers.csv
│   │   ├── products.csv
│   │   ├── stores.csv
│   │   └── orders.csv
│   └── processed/                    # ingest.py output (gitignored)
│       ├── customers.parquet
│       ├── products.parquet
│       ├── stores.parquet
│       ├── orders.parquet
│       └── quarantine/
│           └── orders_rejected.parquet
│
├── lake/
│   ├── __init__.py
│   ├── generate_data.py              # synthetic e-commerce data generator
│   └── ingest.py                     # Polars cleaning: raw -> processed
│
├── warehouse/
│   ├── __init__.py
│   ├── schema.sql                    # star schema DDL (4 dims + 1 fact)
│   ├── load.py                       # DuckDB join -> PyArrow -> psycopg2 -> Postgres
│   └── queries/
│       ├── 01_basic.sql              # SELECT/WHERE/GROUP BY/JOIN
│       ├── 02_intermediate.sql       # subqueries/CASE/multi-joins
│       ├── 03_advanced.sql           # CTEs/recursive CTE/pivot/set ops
│       └── 04_window_functions.sql   # RANK/LAG/LEAD/running totals/NTILE
│
├── src/
│   ├── __init__.py
│   └── logger.py                     # shared logging config, used everywhere
│
├── scripts/
│   └── run_pipeline.sh               # generate -> ingest -> load, fail-fast
│
├── tests/
│   ├── __init__.py
│   ├── test_ingest.py                # 14 tests
│   └── test_load.py                  # 7 tests
│
└── logs/                             # pipeline.log (gitignored)
```