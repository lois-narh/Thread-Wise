-- name: KPIs
SELECT COUNT(*) AS "Orders",
       ROUND(100.0 * AVG(is_late), 1) AS "Late rate %",
       ROUND(AVG(CASE WHEN is_late = 1 THEN days_late END), 1) AS "Avg days late",
       ROUND(SUM(price_ghs) / 1000.0, 0) AS "Revenue (GHS k)",
       SUM(CASE WHEN delivered_date IS NULL
                 AND promised_date < (SELECT MAX(order_date) FROM orders_clean) THEN 1 ELSE 0 END) AS "Open & overdue"
FROM orders_clean;