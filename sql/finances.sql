-- name: KPIs
-- note: Money in = full price of delivered orders + deposits paid on pending orders.
SELECT ROUND(SUM(CASE WHEN delivered_date IS NOT NULL THEN COALESCE(price_ghs, 0)
                      ELSE COALESCE(deposit_ghs, 0) END)) AS "Money in (GHS)",
       ROUND(SUM(CASE WHEN delivered_date IS NULL
                      THEN COALESCE(price_ghs, 0) - COALESCE(deposit_ghs, 0) ELSE 0 END)) AS "Still owed (GHS)",
       ROUND(AVG(price_ghs)) AS "Average order (GHS)",
       ROUND(SUM(CASE WHEN delivered_date IS NULL THEN COALESCE(deposit_ghs, 0) ELSE 0 END)) AS "Deposits on pending (GHS)"
FROM orders_clean;

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

-- name: Money in by garment type (GHS)
-- note: Which garments bring in the most money.
-- chart: bar money_in_ghs
SELECT garment_type, ROUND(SUM(CASE WHEN delivered_date IS NOT NULL THEN COALESCE(price_ghs, 0)
                                    ELSE COALESCE(deposit_ghs, 0) END)) AS money_in_ghs
FROM orders_clean
GROUP BY garment_type
ORDER BY money_in_ghs DESC;

-- name: Biggest unpaid balances
-- note: Pending orders where the customer still owes the most. Chase these before delivery.
SELECT o.order_id AS "Order", c.name AS "Customer", c.phone AS "Phone", o.garment_type AS "Garment",
       o.price_ghs AS "Price (GHS)", o.deposit_ghs AS "Deposit (GHS)",
       ROUND(COALESCE(o.price_ghs, 0) - COALESCE(o.deposit_ghs, 0)) AS "Balance (GHS)"
FROM orders_clean o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.delivered_date IS NULL
ORDER BY "Balance (GHS)" DESC
LIMIT 10;

-- name: Top 10 customers by spend
-- note: Your best customers. Worth a thank-you before the festive rush.
SELECT c.name AS "Customer", c.city AS "City", COUNT(*) AS "Orders",
       ROUND(SUM(COALESCE(o.price_ghs, 0))) AS "Total spent (GHS)"
FROM orders_clean o
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.customer_id
ORDER BY SUM(COALESCE(o.price_ghs, 0)) DESC
LIMIT 10;