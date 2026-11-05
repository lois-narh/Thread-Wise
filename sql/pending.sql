-- name: KPIs
-- note: Counted as of the latest order date in the data.
WITH today AS (SELECT MAX(order_date) AS d FROM orders_clean)
SELECT COUNT(*) AS "Pending",
       SUM(CASE WHEN promised_date < d THEN 1 ELSE 0 END) AS "Overdue",
       SUM(CASE WHEN promised_date >= d AND promised_date <= date(d, '+7 days') THEN 1 ELSE 0 END) AS "Due in next 7 days",
       ROUND(SUM(COALESCE(price_ghs, 0) - COALESCE(deposit_ghs, 0))) AS "Balance owed (GHS)"
FROM orders_clean, today
WHERE delivered_date IS NULL;

-- name: Pending orders per tailor
-- note: Who has the most work in the workshop right now.
-- chart: bar pending_orders
SELECT t.name AS tailor, COUNT(*) AS pending_orders
FROM orders_clean o
JOIN tailors t ON t.tailor_id = o.tailor_id
WHERE o.delivered_date IS NULL
GROUP BY t.tailor_id
ORDER BY pending_orders DESC;

-- name: All pending orders
-- note: Oldest promise first. Balance is what the customer still owes.
SELECT o.order_id AS "Order", c.name AS "Customer", c.phone AS "Phone", t.name AS "Tailor",
       o.garment_type AS "Garment", o.promised_date AS "Promised",
       MAX(0, CAST(julianday((SELECT MAX(order_date) FROM orders_clean)) - julianday(o.promised_date) AS INTEGER)) AS "Days overdue",
       ROUND(COALESCE(o.price_ghs, 0) - COALESCE(o.deposit_ghs, 0)) AS "Balance (GHS)"
FROM orders_clean o
JOIN customers c ON c.customer_id = o.customer_id
JOIN tailors t ON t.tailor_id = o.tailor_id
WHERE o.delivered_date IS NULL
ORDER BY o.promised_date;