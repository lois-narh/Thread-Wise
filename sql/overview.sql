-- name: KPIs
-- note: The shop at a glance. Money in = full price for delivered orders + deposits on pending orders.
SELECT COUNT(*) AS "Orders",
       SUM(CASE WHEN delivered_date IS NULL THEN 1 ELSE 0 END) AS "Pending",
       SUM(CASE WHEN delivered_date IS NOT NULL THEN 1 ELSE 0 END) AS "Delivered",
       SUM(CASE WHEN delivered_date IS NULL
                 AND promised_date < (SELECT MAX(order_date) FROM orders_clean) THEN 1 ELSE 0 END) AS "Pending & overdue",
       ROUND(SUM(CASE WHEN delivered_date IS NOT NULL THEN COALESCE(price_ghs, 0)
                      ELSE COALESCE(deposit_ghs, 0) END)) AS "Money in (GHS)",
       ROUND(SUM(CASE WHEN delivered_date IS NULL
                      THEN COALESCE(price_ghs, 0) - COALESCE(deposit_ghs, 0) ELSE 0 END)) AS "Still owed (GHS)"
FROM orders_clean;

-- name: Orders per month (last 12 months)
-- note: How busy the shop has been.
-- chart: bar orders
WITH m AS (
    SELECT strftime('%Y-%m', order_date) AS month, COUNT(*) AS orders
    FROM orders_clean GROUP BY month ORDER BY month DESC LIMIT 12
)
SELECT month, orders FROM m ORDER BY month;

-- name: Needs attention: most overdue pending orders
-- note: Promised date has passed and the order is still in the workshop. Call these customers first.
SELECT o.order_id AS "Order", c.name AS "Customer", c.phone AS "Phone", t.name AS "Tailor",
       o.garment_type AS "Garment", o.promised_date AS "Promised",
       CAST(julianday((SELECT MAX(order_date) FROM orders_clean)) - julianday(o.promised_date) AS INTEGER) AS "Days overdue"
FROM orders_clean o
JOIN customers c ON c.customer_id = o.customer_id
JOIN tailors t ON t.tailor_id = o.tailor_id
WHERE o.delivered_date IS NULL
  AND o.promised_date < (SELECT MAX(order_date) FROM orders_clean)
ORDER BY o.promised_date
LIMIT 5;