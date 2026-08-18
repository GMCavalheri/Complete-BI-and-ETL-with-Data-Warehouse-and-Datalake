-- =============================================================================
-- 02_intermediate.sql
-- Intermediate SQL: multi-table joins, subqueries (scalar / IN / correlated),
-- CASE expressions, COUNT(DISTINCT ...), and LEFT JOIN / anti-join patterns.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1. Multi-table JOIN (all 5 tables)
-- "Full detail listing: every order line with customer, product, store, and
--  calendar context." A star schema's whole point is that this stays simple
--  even with 4 dimensions involved — every join is on a single key column.
-- -----------------------------------------------------------------------------
SELECT
    f.order_id,
    c.first_name || ' ' || c.last_name AS customer,
    p.product_name,
    p.category,
    s.store_name,
    d.full_date,
    d.month_name,
    f.channel,
    f.quantity,
    f.revenue
FROM fact_sales f
JOIN dim_customer c ON f.customer_key = c.customer_key
JOIN dim_product p  ON f.product_key  = p.product_key
JOIN dim_store s    ON f.store_key    = s.store_key
JOIN dim_date d      ON f.date_key     = d.date_key
ORDER BY f.order_id
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q2. Revenue by month (multi-table join + GROUP BY on dimension attributes)
-- "How does revenue trend month over month across the whole dataset?"
-- -----------------------------------------------------------------------------
SELECT
    d.year,
    d.month,
    d.month_name,
    SUM(f.revenue) AS monthly_revenue,
    COUNT(*)       AS num_orders
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;


-- -----------------------------------------------------------------------------
-- Q3. CASE expression
-- "Bucket every order line into a revenue size tier."
-- -----------------------------------------------------------------------------
SELECT
    f.order_id,
    f.revenue,
    CASE
        WHEN f.revenue < 50   THEN 'Small'
        WHEN f.revenue < 200  THEN 'Medium'
        WHEN f.revenue < 1000 THEN 'Large'
        ELSE 'Very Large'
    END AS revenue_tier
FROM fact_sales f
ORDER BY f.revenue DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q4. CASE inside an aggregate (conditional counting)
-- "How many orders fall into each revenue tier, and what share of total
--  revenue does each tier represent?" A very common reporting pattern:
--  CASE turns a row-level condition into a column you can then aggregate.
-- -----------------------------------------------------------------------------
SELECT
    CASE
        WHEN revenue < 50   THEN '1. Small (<$50)'
        WHEN revenue < 200  THEN '2. Medium ($50-200)'
        WHEN revenue < 1000 THEN '3. Large ($200-1000)'
        ELSE '4. Very Large (>$1000)'
    END AS revenue_tier,
    COUNT(*)                                          AS num_orders,
    SUM(revenue)                                       AS tier_revenue,
    ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 2) AS pct_of_total_revenue
FROM fact_sales
GROUP BY 1
ORDER BY 1;


-- -----------------------------------------------------------------------------
-- Q5. Scalar subquery
-- "Which orders generated more revenue than the overall average?"
-- The subquery runs once and returns a single value, which the outer
-- query then compares every row against.
-- -----------------------------------------------------------------------------
SELECT
    order_id,
    revenue
FROM fact_sales
WHERE revenue > (SELECT AVG(revenue) FROM fact_sales)
ORDER BY revenue DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q6. Subquery with IN
-- "List customers who have placed an order through the 'marketplace' channel."
-- -----------------------------------------------------------------------------
SELECT
    customer_id,
    first_name,
    last_name,
    country
FROM dim_customer
WHERE customer_key IN (
    SELECT DISTINCT customer_key
    FROM fact_sales
    WHERE channel = 'marketplace'
)
ORDER BY customer_id
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q7. Correlated subquery
-- "For each customer, find their single highest-revenue order."
-- Unlike Q5's subquery (computed once), this one re-runs for every row
-- of the outer query, because it references the outer row's customer_key.
-- -----------------------------------------------------------------------------
SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    f.order_id,
    f.revenue
FROM fact_sales f
JOIN dim_customer c ON f.customer_key = c.customer_key
WHERE f.revenue = (
    SELECT MAX(f2.revenue)
    FROM fact_sales f2
    WHERE f2.customer_key = f.customer_key
)
ORDER BY f.revenue DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q8. COUNT(DISTINCT ...)
-- "How many unique customers bought from each product category?"
-- -----------------------------------------------------------------------------
SELECT
    p.category,
    COUNT(DISTINCT f.customer_key) AS unique_customers,
    COUNT(*)                        AS total_line_items
FROM fact_sales f
JOIN dim_product p ON f.product_key = p.product_key
GROUP BY p.category
ORDER BY unique_customers DESC;


-- -----------------------------------------------------------------------------
-- Q9. LEFT JOIN + anti-join pattern (find rows with NO match)
-- "Which customers have never placed an order?" A LEFT JOIN keeps every
-- row from dim_customer even when there's no matching fact_sales row —
-- those rows get NULLs in the fact columns, which is exactly what
-- `WHERE f.order_id IS NULL` filters down to.
-- -----------------------------------------------------------------------------
-- Note: with 60k orders spread across 3,000 customers (~20 orders/customer
-- on average), this will likely return 0 rows on the generated dataset —
-- that's a correct result, not a bug. The pattern is what matters: swap
-- in a lower num_orders in config.yaml and regenerate to see it populated.
SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    c.email
FROM dim_customer c
LEFT JOIN fact_sales f ON c.customer_key = f.customer_key
WHERE f.order_id IS NULL
ORDER BY c.customer_id
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q10. INNER JOIN vs LEFT JOIN comparison
-- "How many products have NEVER been sold?" Same anti-join idea, applied
-- to the product dimension instead of customers.
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS products_never_sold
FROM dim_product p
LEFT JOIN fact_sales f ON p.product_key = f.product_key
WHERE f.order_id IS NULL;
