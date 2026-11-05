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

-- name: Money in per month (last 12 months, GHS)
-- note: Delivered orders count at full price, pending orders at the deposit paid so far.
-- chart: bar money_in_ghs
WITH m AS (
    SELECT strftime('%Y-%m', order_date) AS month,
           ROUND(SUM(CASE WHEN delivered_date IS NOT NULL THEN COALESCE(price_ghs, 0)
                          ELSE COALESCE(deposit_ghs, 0) END)) AS money_in_ghs
    FROM orders_clean GROUP BY month ORDER BY month DESC LIMIT 12
)
SELECT month, money_in_ghs FROM m ORDER BY month;

-- name: Pending orders, most overdue first
-- note: Orders still in the workshop. Balance is what the customer still owes.
SELECT o.order_id, c.name AS customer, t.name AS tailor, o.garment_type, o.promised_date,
       MAX(0, CAST(julianday((SELECT MAX(order_date) FROM orders_clean)) - julianday(o.promised_date) AS INTEGER)) AS days_overdue,
       ROUND(COALESCE(o.price_ghs, 0) - COALESCE(o.deposit_ghs, 0)) AS balance_ghs
FROM orders_clean o
JOIN customers c ON c.customer_id = o.customer_id
JOIN tailors t ON t.tailor_id = o.tailor_id
WHERE o.delivered_date IS NULL
ORDER BY o.promised_date
LIMIT 15;