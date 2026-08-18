-- =============================================================================
-- 03_advanced.sql
-- Advanced SQL: CTEs (including chained and recursive), pivoting via
-- conditional aggregation, set operations, and self-joins.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1. CTE (WITH clause)
-- "Which customers are in the top 5% by total spend?"
-- A CTE names a subquery so the main query reads top-to-bottom instead of
-- nesting parentheses — same result as a subquery, much more readable
-- once you're combining several steps.
-- -----------------------------------------------------------------------------
WITH customer_spend AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        SUM(f.revenue) AS total_spend
    FROM fact_sales f
    JOIN dim_customer c ON f.customer_key = c.customer_key
    GROUP BY c.customer_id, c.first_name, c.last_name
),
spend_threshold AS (
    SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_spend) AS p95
    FROM customer_spend
)
SELECT cs.*
FROM customer_spend cs, spend_threshold st
WHERE cs.total_spend >= st.p95
ORDER BY cs.total_spend DESC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q2. Multiple chained CTEs
-- "Compare each product category's revenue this year vs. last year, and
--  the % change." Breaking this into named steps (yearly totals, then the
--  comparison) is far easier to follow than one deeply nested query.
-- -----------------------------------------------------------------------------
WITH yearly_category_revenue AS (
    SELECT
        p.category,
        d.year,
        SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY p.category, d.year
),
this_year AS (
    SELECT category, revenue FROM yearly_category_revenue WHERE year = 2025
),
last_year AS (
    SELECT category, revenue FROM yearly_category_revenue WHERE year = 2024
)
SELECT
    ty.category,
    ly.revenue AS revenue_2024,
    ty.revenue AS revenue_2025,
    ROUND(100.0 * (ty.revenue - ly.revenue) / ly.revenue, 2) AS pct_change
FROM this_year ty
JOIN last_year ly ON ty.category = ly.category
ORDER BY pct_change DESC;


-- -----------------------------------------------------------------------------
-- Q3. Recursive CTE
-- "Build a month-by-month revenue trend, including months with zero
--  orders, without relying on dim_date." A recursive CTE generates the
--  full month sequence itself: the base case picks the first month, the
--  recursive part keeps adding one month until it passes the end date.
-- This is the classic "generate a series" use of recursion in SQL — the
-- same technique applies to org charts, category trees, or any
-- parent-child hierarchy.
-- -----------------------------------------------------------------------------
WITH RECURSIVE month_sequence AS (
    SELECT DATE '2023-01-01' AS month_start   -- base case (anchor)

    UNION ALL

    SELECT (month_start + INTERVAL '1 month')::date
    FROM month_sequence
    WHERE month_start < DATE '2025-12-01'      -- recursive step + stop condition
)
SELECT
    ms.month_start,
    COALESCE(SUM(f.revenue), 0) AS revenue
FROM month_sequence ms
LEFT JOIN dim_date d ON d.year = EXTRACT(YEAR FROM ms.month_start)
                      AND d.month = EXTRACT(MONTH FROM ms.month_start)
LEFT JOIN fact_sales f ON f.date_key = d.date_key
GROUP BY ms.month_start
ORDER BY ms.month_start;


-- -----------------------------------------------------------------------------
-- Q4. Pivoting via conditional aggregation
-- "Show quarterly revenue per category as a pivot table: one row per
--  category, one column per quarter." Postgres has no native PIVOT
--  keyword — this is the standard way to do it: FILTER (or CASE) inside
--  an aggregate, one expression per output column.
-- -----------------------------------------------------------------------------
SELECT
    p.category,
    SUM(f.revenue) FILTER (WHERE d.quarter = 1) AS q1_revenue,
    SUM(f.revenue) FILTER (WHERE d.quarter = 2) AS q2_revenue,
    SUM(f.revenue) FILTER (WHERE d.quarter = 3) AS q3_revenue,
    SUM(f.revenue) FILTER (WHERE d.quarter = 4) AS q4_revenue,
    SUM(f.revenue) AS total_revenue
FROM fact_sales f
JOIN dim_product p ON f.product_key = p.product_key
JOIN dim_date d ON f.date_key = d.date_key
WHERE d.year = 2025
GROUP BY p.category
ORDER BY total_revenue DESC;


-- -----------------------------------------------------------------------------
-- Q5. Set operations — UNION
-- "Single combined list of every customer_id and store_id that appears in
--  a marketplace order — two structurally different entities, tagged by
--  type." UNION also de-duplicates automatically (UNION ALL would keep
--  duplicates, useful when you specifically want to preserve them).
-- -----------------------------------------------------------------------------
SELECT DISTINCT 'customer' AS entity_type, customer_id AS entity_id
FROM dim_customer c
JOIN fact_sales f ON c.customer_key = f.customer_key
WHERE f.channel = 'marketplace'

UNION

SELECT DISTINCT 'store' AS entity_type, store_id AS entity_id
FROM dim_store s
JOIN fact_sales f ON s.store_key = f.store_key
WHERE f.channel = 'marketplace'

ORDER BY entity_type, entity_id
LIMIT 20;


-- -----------------------------------------------------------------------------
-- Q6. Set operations — INTERSECT
-- "Which customers bought Electronics AND Beauty products?" INTERSECT
-- returns only rows that appear in both result sets — a clean alternative
-- to writing two joins + a HAVING COUNT(DISTINCT category) = 2.
-- -----------------------------------------------------------------------------
SELECT c.customer_id, c.first_name, c.last_name
FROM dim_customer c
JOIN fact_sales f ON c.customer_key = f.customer_key
JOIN dim_product p ON f.product_key = p.product_key
WHERE p.category = 'Electronics'

INTERSECT

SELECT c.customer_id, c.first_name, c.last_name
FROM dim_customer c
JOIN fact_sales f ON c.customer_key = f.customer_key
JOIN dim_product p ON f.product_key = p.product_key
WHERE p.category = 'Beauty'

ORDER BY 1
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q7. Self-JOIN
-- "For each store, find other stores in the same country (potential
--  market overlap check)." A self-join compares a table to itself —
-- here, matching stores on `country` while excluding a store matching
-- itself. (We use country rather than city: with only 25 stores spread
-- across Faker's full city list, city collisions are rare to nonexistent
-- in this generated dataset, while country collisions do occur.)
-- -----------------------------------------------------------------------------
SELECT
    s1.store_name AS store_a,
    s2.store_name AS store_b,
    s1.country
FROM dim_store s1
JOIN dim_store s2
    ON s1.country = s2.country
    AND s1.store_key < s2.store_key   -- avoids duplicate pairs (A,B) and (B,A), and self-pairs
ORDER BY s1.country
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q8. CTE + window function combined
-- "Rank product categories by revenue within each quarter of 2025."
-- Previews the window-function file that follows — CTEs and window
-- functions are used together constantly in real reporting queries.
-- -----------------------------------------------------------------------------
WITH quarterly_category_revenue AS (
    SELECT
        d.quarter,
        p.category,
        SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE d.year = 2025
    GROUP BY d.quarter, p.category
)
SELECT
    quarter,
    category,
    revenue,
    RANK() OVER (PARTITION BY quarter ORDER BY revenue DESC) AS revenue_rank
FROM quarterly_category_revenue
ORDER BY quarter, revenue_rank
LIMIT 20;
