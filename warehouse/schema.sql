-- =============================================================================
-- schema.sql
-- Data Warehouse schema — PostgreSQL
--
-- Design: STAR SCHEMA
-- --------------------
-- A star schema separates data into:
--   - DIMENSION tables: descriptive attributes you filter/group by
--     (who, what, where, when). Small-ish, slowly changing.
--   - FACT tables: the measurable events/transactions (what happened,
--     how much). Large, one row per event, mostly foreign keys + numbers.
--
-- This shape is the industry-standard for analytical warehouses (as
-- opposed to the normalized 3NF schema you'd use for a transactional
-- app) because it makes analytical SQL fast and intuitive: you join a
-- big fact table to a handful of small dimension tables, instead of
-- traversing many normalized tables.
--
-- Visually, fact_sales sits in the middle with dimensions radiating out
-- from it — hence "star":
--
--            dim_customer      dim_product
--                    \            /
--                     \          /
--                      fact_sales
--                     /          \
--                    /            \
--            dim_store         dim_date
--
-- Naming convention: each dimension has its own surrogate primary key
-- (a warehouse-generated integer, suffixed `_key`) in addition to the
-- natural/business key from the source system (`_id`). This is standard
-- warehouse practice — surrogate keys let the warehouse evolve
-- independently of the source system's ID scheme, and they're what
-- fact tables reference.
-- =============================================================================

DROP TABLE IF EXISTS fact_sales CASCADE;
DROP TABLE IF EXISTS dim_customer CASCADE;
DROP TABLE IF EXISTS dim_product CASCADE;
DROP TABLE IF EXISTS dim_store CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;


-- -----------------------------------------------------------------------------
-- DIM_CUSTOMER
-- -----------------------------------------------------------------------------
CREATE TABLE dim_customer (
    customer_key    SERIAL PRIMARY KEY,          -- surrogate key (warehouse-generated)
    customer_id     INTEGER NOT NULL UNIQUE,      -- natural key (from source system)
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    signup_date     DATE,
    city            VARCHAR(150),                 -- nullable: source data has gaps (by design)
    country         VARCHAR(150) NOT NULL,
    loaded_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE dim_customer IS 'Customer dimension. One row per customer_id after dedup/cleaning in the lake ingestion step.';


-- -----------------------------------------------------------------------------
-- DIM_PRODUCT
-- -----------------------------------------------------------------------------
CREATE TABLE dim_product (
    product_key     SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL UNIQUE,
    product_name    VARCHAR(255) NOT NULL,
    category        VARCHAR(100) NOT NULL,
    unit_price      NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    loaded_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE dim_product IS 'Product catalog dimension.';


-- -----------------------------------------------------------------------------
-- DIM_STORE
-- -----------------------------------------------------------------------------
CREATE TABLE dim_store (
    store_key       SERIAL PRIMARY KEY,
    store_id        INTEGER NOT NULL UNIQUE,
    store_name      VARCHAR(255) NOT NULL,
    city            VARCHAR(150) NOT NULL,
    country         VARCHAR(150) NOT NULL,
    loaded_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE dim_store IS 'Store/channel-location dimension.';


-- -----------------------------------------------------------------------------
-- DIM_DATE
-- -----------------------------------------------------------------------------
-- A classic warehouse pattern: instead of extracting year/month/weekday
-- with SQL functions every time you query, you pre-compute them once
-- into a date dimension and just join. Makes time-based grouping
-- (by month, by quarter, weekday-vs-weekend, etc.) trivial and fast.
-- date_key uses the YYYYMMDD integer convention (e.g. 2024-03-05 -> 20240305).
-- -----------------------------------------------------------------------------
CREATE TABLE dim_date (
    date_key        INTEGER PRIMARY KEY,          -- e.g. 20240305
    full_date       DATE NOT NULL UNIQUE,
    day             SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    month_name      VARCHAR(20) NOT NULL,
    quarter         SMALLINT NOT NULL,
    year            SMALLINT NOT NULL,
    day_of_week     SMALLINT NOT NULL,             -- 0=Sunday .. 6=Saturday
    day_name        VARCHAR(20) NOT NULL,
    is_weekend      BOOLEAN NOT NULL
);

COMMENT ON TABLE dim_date IS 'Pre-computed calendar dimension for fast time-based analysis. Populated programmatically, see warehouse/load.py.';


-- -----------------------------------------------------------------------------
-- FACT_SALES
-- -----------------------------------------------------------------------------
-- Grain: one row per order line item (one product, one order, one customer,
-- one store, one date). This is the most important design decision in a
-- star schema — always state the grain explicitly.
-- -----------------------------------------------------------------------------
CREATE TABLE fact_sales (
    sale_id         BIGSERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL,             -- natural key from source, not unique here
                                                    -- (kept for traceability back to raw data)
    customer_key    INTEGER NOT NULL REFERENCES dim_customer (customer_key),
    product_key     INTEGER NOT NULL REFERENCES dim_product (product_key),
    store_key       INTEGER NOT NULL REFERENCES dim_store (store_key),
    date_key        INTEGER NOT NULL REFERENCES dim_date (date_key),
    channel         VARCHAR(50) NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),  -- bad rows (null/negative) are
                                                              -- rejected during cleaning, not loaded here
    unit_price      NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    revenue         NUMERIC(12, 2) NOT NULL CHECK (revenue >= 0),  -- quantity * unit_price, precomputed
    loaded_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE fact_sales IS 'Fact table. Grain: one row per order line item.';

-- -----------------------------------------------------------------------------
-- INDEXES
-- -----------------------------------------------------------------------------
-- Foreign keys in Postgres are NOT automatically indexed (unlike primary
-- keys). Since almost every analytical query joins fact_sales to its
-- dimensions and/or filters by date, these indexes matter a lot for
-- query performance once the fact table has tens of thousands of rows.
CREATE INDEX idx_fact_sales_customer_key ON fact_sales (customer_key);
CREATE INDEX idx_fact_sales_product_key  ON fact_sales (product_key);
CREATE INDEX idx_fact_sales_store_key    ON fact_sales (store_key);
CREATE INDEX idx_fact_sales_date_key     ON fact_sales (date_key);
CREATE INDEX idx_fact_sales_order_id     ON fact_sales (order_id);
