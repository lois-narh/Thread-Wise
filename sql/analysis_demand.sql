-- name: Weekly orders with 4-week moving average
-- note: A window function smooths week-to-week noise so the seasonal build-up before December and Easter is visible.
-- chart: line orders,moving_avg_4w
WITH weekly AS (
    SELECT date(order_date, 'weekday 0', '-6 days') AS week_start, COUNT(*) AS orders
    FROM orders_clean GROUP BY week_start
)
SELECT week_start, orders,
       ROUND(AVG(orders) OVER (ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 1) AS moving_avg_4w
FROM weekly
ORDER BY week_start;

-- name: Average orders per week, by month
-- note: The shape of the year. Use it to decide when to hire seasonal help and buy fabric early.
-- chart: bar avg_orders_per_week
WITH weekly AS (
    SELECT date(order_date, 'weekday 0', '-6 days') AS week_start, COUNT(*) AS orders
    FROM orders_clean GROUP BY week_start
)
SELECT printf('%02d ', CAST(strftime('%m', week_start) AS INTEGER))
           || SUBSTR('JanFebMarAprMayJunJulAugSepOctNovDec', 3 * (CAST(strftime('%m', week_start) AS INTEGER) - 1) + 1, 3) AS month,
       COUNT(*) AS weeks_observed,
       ROUND(AVG(orders), 1) AS avg_orders_per_week
FROM weekly
GROUP BY strftime('%m', week_start)
ORDER BY strftime('%m', week_start);

-- name: Demand by garment type
-- note: Which garments drive volume. The share column uses a window over the whole table.
-- chart: bar share_pct
SELECT garment_type, COUNT(*) AS orders,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct
FROM orders_clean
GROUP BY garment_type
ORDER BY orders DESC;

-- name: Ten busiest weeks
-- note: RANK() picks out the peak weeks. These are the weeks to plan capacity for.
WITH weekly AS (
    SELECT date(order_date, 'weekday 0', '-6 days') AS week_start, COUNT(*) AS orders,
           SUM(CASE WHEN is_rush = 1 THEN 1 ELSE 0 END) AS rush_orders
    FROM orders_clean GROUP BY week_start
),
ranked AS (
    SELECT *, RANK() OVER (ORDER BY orders DESC) AS busiest_rank FROM weekly
)
SELECT busiest_rank, week_start, orders, rush_orders
FROM ranked
WHERE busiest_rank <= 10
ORDER BY busiest_rank, week_start;