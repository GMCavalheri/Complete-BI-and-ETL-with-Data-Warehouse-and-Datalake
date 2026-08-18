-- =============================================================================
-- 04_window_functions.sql
-- Window functions: the feature that separates "knows SQL" from "knows SQL
-- for analytics." Unlike GROUP BY (which collapses rows), a window function
-- computes a value across a set of related rows while keeping every row
-- in the output — this is what makes running totals, rankings, and
-- period-over-period comparisons possible in a single query.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1. ROW_NUMBER, RANK, DENSE_RANK — the difference matters
-- "Rank products by total revenue, three ways."
-- ROW_NUMBER: always unique (1,2,3,4...), arbitrarily breaks ties.
-- RANK: ties share a rank, but the next rank skips (1,1,3,4...).
-- DENSE_RANK: ties share a rank, next rank does NOT skip (1,1,2,3...).
-- -----------------------------------------------------------------------------
WITH product_revenue AS (
    SELECT p.product_name, p.category, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    GROUP BY p.product_name, p.category
)
SELECT
    product_name,
    category,
    revenue,
    ROW_NUMBER() OVER (ORDER BY revenue DESC) AS row_num,
    RANK()       OVER (ORDER BY revenue DESC) AS rnk,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS dense_rnk
FROM product_revenue
ORDER BY revenue DESC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q2. Top-N per group
-- "The top 3 best-selling products WITHIN EACH CATEGORY." This is the
-- single most common real-world use of window functions: PARTITION BY
-- resets the ranking for every category, so "top 3" means top 3 per
-- category, not top 3 overall.
-- -----------------------------------------------------------------------------
WITH product_revenue AS (
    SELECT
        p.category,
        p.product_name,
        SUM(f.revenue) AS revenue,
        ROW_NUMBER() OVER (PARTITION BY p.category ORDER BY SUM(f.revenue) DESC) AS rank_in_category
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    GROUP BY p.category, p.product_name
)
SELECT category, product_name, revenue, rank_in_category
FROM product_revenue
WHERE rank_in_category <= 3
ORDER BY category, rank_in_category;


-- -----------------------------------------------------------------------------
-- Q3. Running total
-- "Cumulative revenue by month, 2025." SUM() OVER (ORDER BY ...) with no
-- PARTITION BY, using the default frame (start of the result set through
-- the current row), gives a running total instead of a single grand total.
-- -----------------------------------------------------------------------------
WITH monthly_revenue AS (
    SELECT d.month, d.month_name, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE d.year = 2025
    GROUP BY d.month, d.month_name
)
SELECT
    month,
    month_name,
    revenue,
    SUM(revenue) OVER (ORDER BY month) AS running_total
FROM monthly_revenue
ORDER BY month;


-- -----------------------------------------------------------------------------
-- Q4. Moving average
-- "3-month moving average of revenue, to smooth out month-to-month noise."
-- ROWS BETWEEN 2 PRECEDING AND CURRENT ROW explicitly defines the frame:
-- "this row and the 2 rows before it" — i.e. a trailing 3-month window.
-- -----------------------------------------------------------------------------
WITH monthly_revenue AS (
    SELECT d.year, d.month, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.year, d.month
)
SELECT
    year,
    month,
    revenue,
    ROUND(
        AVG(revenue) OVER (ORDER BY year, month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
        2
    ) AS moving_avg_3mo
FROM monthly_revenue
ORDER BY year, month;


-- -----------------------------------------------------------------------------
-- Q5. LAG — month-over-month growth
-- "What was the % change in revenue vs. the previous month?" LAG(x, 1)
-- pulls the value of `x` from the row 1 position before the current one
-- (within the ORDER BY), letting you compare a row directly to its
-- predecessor without a self-join.
-- -----------------------------------------------------------------------------
WITH monthly_revenue AS (
    SELECT d.year, d.month, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.year, d.month
)
SELECT
    year,
    month,
    revenue,
    LAG(revenue, 1) OVER (ORDER BY year, month) AS prev_month_revenue,
    ROUND(
        100.0 * (revenue - LAG(revenue, 1) OVER (ORDER BY year, month))
        / LAG(revenue, 1) OVER (ORDER BY year, month),
        2
    ) AS pct_change_mom
FROM monthly_revenue
ORDER BY year, month;


-- -----------------------------------------------------------------------------
-- Q6. LEAD — look-ahead comparison
-- "For each customer's orders in date order, how many days until their
--  NEXT order?" LEAD is LAG's mirror image: it looks forward instead of
-- back. This kind of gap-between-events calculation is the basis of
-- churn/retention analysis (e.g. "average days between purchases").
-- -----------------------------------------------------------------------------
WITH customer_orders AS (
    SELECT
        f.customer_key,
        d.full_date AS order_date,
        f.order_id
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
)
SELECT
    customer_key,
    order_id,
    order_date,
    LEAD(order_date, 1) OVER (PARTITION BY customer_key ORDER BY order_date) AS next_order_date,
    LEAD(order_date, 1) OVER (PARTITION BY customer_key ORDER BY order_date) - order_date AS days_until_next_order
FROM customer_orders
ORDER BY customer_key, order_date
LIMIT 20;


-- -----------------------------------------------------------------------------
-- Q7. NTILE — customer segmentation into quartiles
-- "Split all customers into 4 equal-sized groups (quartiles) by total
--  spend, from highest to lowest." NTILE(4) is a fast way to build simple
-- tiers (e.g. for a "VIP / High / Medium / Low" customer segmentation)
-- without manually picking cutoff values.
-- -----------------------------------------------------------------------------
WITH customer_spend AS (
    SELECT c.customer_id, c.first_name, c.last_name, SUM(f.revenue) AS total_spend
    FROM fact_sales f
    JOIN dim_customer c ON f.customer_key = c.customer_key
    GROUP BY c.customer_id, c.first_name, c.last_name
)
SELECT
    customer_id,
    first_name,
    last_name,
    total_spend,
    NTILE(4) OVER (ORDER BY total_spend DESC) AS spend_quartile  -- 1 = top spenders
FROM customer_spend
ORDER BY total_spend DESC
LIMIT 20;


-- -----------------------------------------------------------------------------
-- Q8. Quartile summary (window function feeding a GROUP BY)
-- "What's the revenue range and customer count in each spend quartile
--  from Q7?" Shows a window-function result being aggregated afterward —
-- a very common two-step reporting pattern.
-- -----------------------------------------------------------------------------
WITH customer_spend AS (
    SELECT c.customer_id, SUM(f.revenue) AS total_spend
    FROM fact_sales f
    JOIN dim_customer c ON f.customer_key = c.customer_key
    GROUP BY c.customer_id
),
quartiles AS (
    SELECT
        customer_id,
        total_spend,
        NTILE(4) OVER (ORDER BY total_spend DESC) AS spend_quartile
    FROM customer_spend
)
SELECT
    spend_quartile,
    COUNT(*)             AS num_customers,
    MIN(total_spend)      AS min_spend,
    MAX(total_spend)      AS max_spend,
    ROUND(AVG(total_spend), 2) AS avg_spend
FROM quartiles
GROUP BY spend_quartile
ORDER BY spend_quartile;


-- -----------------------------------------------------------------------------
-- Q9. FIRST_VALUE / LAST_VALUE
-- "For each customer, show their most recent order alongside their
--  very first order — in every row." FIRST_VALUE/LAST_VALUE pull a value
-- from the edge of the window frame; note LAST_VALUE needs an explicit
-- frame (RANGE BETWEEN ... AND UNBOUNDED FOLLOWING) or it only sees up
-- to the current row by default — a classic SQL gotcha worth knowing.
-- -----------------------------------------------------------------------------
WITH customer_orders AS (
    SELECT
        f.customer_key,
        f.order_id,
        d.full_date AS order_date,
        f.revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
)
SELECT DISTINCT
    customer_key,
    FIRST_VALUE(order_date) OVER w AS first_order_date,
    LAST_VALUE(order_date) OVER w  AS most_recent_order_date
FROM customer_orders
WINDOW w AS (
    PARTITION BY customer_key
    ORDER BY order_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
ORDER BY customer_key
LIMIT 15;
