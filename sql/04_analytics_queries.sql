-- 1. Daily sales by product category.
-- Completed orders are used for revenue; all statuses remain available in the
-- fact table for operational reporting.
SELECT
    calendar.full_date AS sales_date,
    product.category,
    COUNT(*) AS order_line_count,
    SUM(sales.quantity) AS units_sold,
    SUM(sales.gross_sales) AS gross_sales,
    SUM(sales.discount) AS discounts,
    SUM(sales.net_sales) AS net_sales
FROM retail_dw.fact_sales AS sales
JOIN retail_dw.dim_date AS calendar
  ON calendar.date_key = sales.date_key
JOIN retail_dw.dim_product AS product
  ON product.product_key = sales.product_key
WHERE sales.order_status = 'completed'
GROUP BY calendar.full_date, product.category
ORDER BY sales_date, product.category;

-- 2. Monthly revenue and change from the previous month with completed sales.
WITH monthly_sales AS (
    SELECT
        DATE_TRUNC('month', calendar.full_date)::date AS sales_month,
        SUM(sales.net_sales) AS net_sales
    FROM retail_dw.fact_sales AS sales
    JOIN retail_dw.dim_date AS calendar
      ON calendar.date_key = sales.date_key
    WHERE sales.order_status = 'completed'
    GROUP BY DATE_TRUNC('month', calendar.full_date)::date
),
monthly_comparison AS (
    SELECT
        sales_month,
        net_sales,
        LAG(net_sales) OVER (ORDER BY sales_month) AS previous_month_net_sales
    FROM monthly_sales
)
SELECT
    sales_month,
    net_sales,
    previous_month_net_sales,
    net_sales - previous_month_net_sales AS change_amount,
    ROUND(
        100.0 * (net_sales - previous_month_net_sales)
        / NULLIF(previous_month_net_sales, 0),
        2
    ) AS change_percent
FROM monthly_comparison
ORDER BY sales_month;

-- 3. Top three products by net sales in each month (ties receive the same rank).
WITH monthly_product_sales AS (
    SELECT
        DATE_TRUNC('month', calendar.full_date)::date AS sales_month,
        product.product_id,
        product.product_name,
        SUM(sales.quantity) AS units_sold,
        SUM(sales.net_sales) AS net_sales
    FROM retail_dw.fact_sales AS sales
    JOIN retail_dw.dim_date AS calendar
      ON calendar.date_key = sales.date_key
    JOIN retail_dw.dim_product AS product
      ON product.product_key = sales.product_key
    WHERE sales.order_status = 'completed'
    GROUP BY
        DATE_TRUNC('month', calendar.full_date)::date,
        product.product_id,
        product.product_name
),
ranked_products AS (
    SELECT
        monthly_product_sales.*,
        DENSE_RANK() OVER (
            PARTITION BY sales_month
            ORDER BY net_sales DESC
        ) AS sales_rank
    FROM monthly_product_sales
)
SELECT
    sales_month,
    product_id,
    product_name,
    units_sold,
    net_sales,
    sales_rank
FROM ranked_products
WHERE sales_rank <= 3
ORDER BY sales_month, sales_rank, product_id;

-- 4. Customer lifetime totals above the average completed order value.
-- The correlated reporting metric is customer lifetime revenue versus the
-- scalar subquery's average completed order value.
WITH customer_sales AS (
    SELECT
        customer.customer_id,
        SUM(sales.net_sales) AS lifetime_net_sales,
        COUNT(DISTINCT sales.order_id) AS completed_orders,
        SUM(sales.quantity) AS units_purchased
    FROM retail_dw.fact_sales AS sales
    JOIN retail_dw.dim_customer AS customer
      ON customer.customer_key = sales.customer_key
    WHERE sales.order_status = 'completed'
    GROUP BY customer.customer_id
)
SELECT
    current_customer.customer_id,
    current_customer.first_name,
    current_customer.last_name,
    customer_sales.completed_orders,
    customer_sales.units_purchased,
    customer_sales.lifetime_net_sales
FROM customer_sales
JOIN retail_dw.dim_customer AS current_customer
  ON current_customer.customer_id = customer_sales.customer_id
 AND current_customer.is_current
WHERE customer_sales.lifetime_net_sales > (
    SELECT AVG(order_sales.net_sales)
    FROM retail_dw.fact_sales AS order_sales
    WHERE order_sales.order_status = 'completed'
)
ORDER BY customer_sales.lifetime_net_sales DESC;

-- 5. Daily cumulative completed revenue and its contribution to total revenue.
WITH daily_sales AS (
    SELECT
        calendar.full_date AS sales_date,
        SUM(sales.net_sales) AS net_sales
    FROM retail_dw.fact_sales AS sales
    JOIN retail_dw.dim_date AS calendar
      ON calendar.date_key = sales.date_key
    WHERE sales.order_status = 'completed'
    GROUP BY calendar.full_date
)
SELECT
    sales_date,
    net_sales,
    SUM(net_sales) OVER (
        ORDER BY sales_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_net_sales,
    ROUND(
        100.0 * net_sales / NULLIF(SUM(net_sales) OVER (), 0),
        2
    ) AS percent_of_total
FROM daily_sales
ORDER BY sales_date;

-- 6. Reconciliation totals by ingestion source and order status.
SELECT
    sales.source,
    sales.order_status,
    COUNT(*) AS order_line_count,
    SUM(sales.quantity) AS units_sold,
    SUM(sales.gross_sales) AS gross_sales,
    SUM(sales.discount) AS discounts,
    SUM(sales.net_sales) AS net_sales,
    COUNT(*) FILTER (WHERE sales.late_arriving) AS late_order_lines
FROM retail_dw.fact_sales AS sales
GROUP BY sales.source, sales.order_status
ORDER BY sales.source, sales.order_status;
