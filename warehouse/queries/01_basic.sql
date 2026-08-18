-- =============================================================================
-- 01_basic.sql
-- Foundational SQL: single-table filtering/sorting, aggregate functions,
-- GROUP BY / HAVING, and simple two-table JOINs.
--
-- Run any query individually against the warehouse, e.g.:
--   psql -h localhost -U dw_user -d dw_lake -f warehouse/queries/01_basic.sql
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1. SELECT + WHERE + ORDER BY + LIMIT
-- "What are the 10 most expensive products in the Electronics category?"
-- -----------------------------------------------------------------------------
SELECT
    product_name,
    category,
    unit_price
FROM dim_product
WHERE category = 'Electronics'
ORDER BY unit_price DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q2. DISTINCT
-- "What product categories do we sell?"
-- -----------------------------------------------------------------------------
SELECT DISTINCT category
FROM dim_product
ORDER BY category;


-- -----------------------------------------------------------------------------
-- Q3. Basic aggregate functions
-- "What's the overall sales performance — total revenue, number of orders,
--  average order value, cheapest/most expensive line item?"
-- -----------------------------------------------------------------------------
SELECT
    COUNT(*)              AS total_line_items,
    SUM(revenue)           AS total_revenue,
    ROUND(AVG(revenue), 2) AS avg_line_item_revenue,
    MIN(revenue)           AS min_line_item_revenue,
    MAX(revenue)           AS max_line_item_revenue
FROM fact_sales;


-- -----------------------------------------------------------------------------
-- Q4. GROUP BY
-- "How much revenue did each sales channel generate?"
-- -----------------------------------------------------------------------------
SELECT
    channel,
    COUNT(*)      AS num_orders,
    SUM(revenue)  AS total_revenue
FROM fact_sales
GROUP BY channel
ORDER BY total_revenue DESC;


-- -----------------------------------------------------------------------------
-- Q5. GROUP BY + HAVING
-- "Which product categories generated more than $500,000 in total revenue?"
-- HAVING filters on the *aggregated* result — WHERE can't do this, because
-- WHERE is evaluated before GROUP BY collapses the rows.
-- -----------------------------------------------------------------------------
SELECT
    p.category,
    SUM(f.revenue) AS total_revenue
FROM fact_sales f
JOIN dim_product p ON f.product_key = p.product_key
GROUP BY p.category
HAVING SUM(f.revenue) > 500000
ORDER BY total_revenue DESC;


-- -----------------------------------------------------------------------------
-- Q6. Simple two-table JOIN
-- "List the 10 most recent orders with the customer's name and product name."
-- -----------------------------------------------------------------------------
SELECT
    f.order_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    p.product_name,
    f.quantity,
    f.revenue,
    d.full_date
FROM fact_sales f
JOIN dim_customer c ON f.customer_key = c.customer_key
JOIN dim_product p  ON f.product_key = p.product_key
JOIN dim_date d     ON f.date_key = d.date_key
ORDER BY d.full_date DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q7. Aggregation with a JOIN + string functions
-- "What's the total revenue per store, along with the store's city?"
-- -----------------------------------------------------------------------------
SELECT
    s.store_name,
    s.city,
    COUNT(*)     AS num_orders,
    SUM(f.revenue) AS total_revenue
FROM fact_sales f
JOIN dim_store s ON f.store_key = s.store_key
GROUP BY s.store_name, s.city
ORDER BY total_revenue DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q8. Filtering on a joined dimension attribute
-- "List all orders placed on a weekend."
-- -----------------------------------------------------------------------------
SELECT
    f.order_id,
    d.full_date,
    d.day_name,
    f.revenue
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
WHERE d.is_weekend = TRUE
ORDER BY d.full_date
LIMIT 10;
