-- name: KPIs
WITH weekly AS (
    SELECT date(order_date, 'weekday 0', '-6 days') AS week_start, COUNT(*) AS n
    FROM orders_clean GROUP BY week_start
),
recent AS (
    SELECT n, ROW_NUMBER() OVER (ORDER BY week_start DESC) AS r FROM weekly
)
SELECT (SELECT COUNT(*) FROM orders_clean) AS "Orders",
       ROUND(AVG(n), 1) AS "Avg orders / week",
       MAX(n) AS "Busiest week",
       ROUND(100.0 * (1.0 * SUM(CASE WHEN r BETWEEN 1 AND 4 THEN n END)
                          / SUM(CASE WHEN r BETWEEN 5 AND 8 THEN n END) - 1), 1) AS "Last 4 weeks vs prior 4 %"
FROM recent;