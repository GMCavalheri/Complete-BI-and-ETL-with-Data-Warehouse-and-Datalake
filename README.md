# Complete BI and ETL with Data Warehouse and Datalake

```
dw-lake-integration/
├── docker-compose.yml
├── config/
│   └── config.yaml
├── data/
│   ├── raw/              # landing zone (lake)
│   └── processed/        # cleaned parquet (lake)
├── lake/
│   ├── generate_data.py  # synthetic data generator
│   ├── ingest.py         # raw -> processed (Polars transforms)
│   └── explore.py        # DuckDB queries on parquet (lake analytics)
├── warehouse/
│   ├── schema.sql        # DDL: dimension & fact tables
│   ├── load.py           # processed parquet -> Postgres (via PyArrow)
│   └── queries/
│       ├── 01_basic.sql
│       ├── 02_intermediate.sql
│       ├── 03_advanced.sql
│       └── 04_window_functions.sql
├── logs/
│   └── (rotating log files, gitignored)
├── tests/
│   ├── test_ingest.py
│   ├── test_load.py
│   └── test_queries.py
├── src/
│   └── logger.py         # shared logging config
├── requirements.txt
└── README.md
dw-lake-integration/
├── docker-compose.yml
├── config/
│   └── config.yaml
├── data/
│   ├── raw/              # landing zone (lake)
│   └── processed/        # cleaned parquet (lake)
├── lake/
│   ├── generate_data.py  # synthetic data generator
│   ├── ingest.py         # raw -> processed (Polars transforms)
│   └── explore.py        # DuckDB queries on parquet (lake analytics)
├── warehouse/
│   ├── schema.sql        # DDL: dimension & fact tables
│   ├── load.py           # processed parquet -> Postgres (via PyArrow)
│   └── queries/
│       ├── 01_basic.sql
│       ├── 02_intermediate.sql
│       ├── 03_advanced.sql
│       └── 04_window_functions.sql
├── logs/
│   └── (rotating log files, gitignored)
├── tests/
│   ├── test_ingest.py
│   ├── test_load.py
│   └── test_queries.py
├── src/
│   └── logger.py         # shared logging config
├── requirements.txt
└── README.md
```