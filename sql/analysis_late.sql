-- name: Late rate by month the order was placed
-- note: Shows when orders run late. A tall bar means orders placed in that month need extra capacity or an earlier start.
-- chart: bar late_pct
SELECT printf('%02d ', CAST(strftime('%m', order_date) AS INTEGER))
           || SUBSTR('JanFebMarAprMayJunJulAugSepOctNovDec', 3 * (CAST(strftime('%m', order_date) AS INTEGER) - 1) + 1, 3) AS month,
       COUNT(*) AS delivered,
       ROUND(100.0 * SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS late_pct
FROM orders_clean
WHERE delivered_date IS NOT NULL
GROUP BY strftime('%m', order_date)
ORDER BY strftime('%m', order_date);

-- name: Late rate by deposit paid
-- note: Compares customers who paid little upfront with those who paid a lot. If the late rate falls as the deposit rises, a minimum deposit is worth trying, since it pays for fabric and trims.
-- chart: bar late_pct
SELECT CASE WHEN deposit_pct < 20 THEN '1) under 20%'
            WHEN deposit_pct < 50 THEN '2) 20-50%'
            ELSE '3) 50% or more' END AS deposit_paid,
       COUNT(*) AS delivered,
       ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM orders_clean
WHERE delivered_date IS NOT NULL AND deposit_pct IS NOT NULL
GROUP BY deposit_paid
ORDER BY deposit_paid;

-- name: Late rate by how busy the tailor was
-- note: For each order, counts how many open orders the tailor already had on the day it was placed (a subquery), then splits orders into four equal groups (a window function). Q1 is the quietest, Q4 the busiest. If lateness climbs with workload, cap how many open orders one tailor can carry.
-- chart: bar late_pct
WITH load AS (
    SELECT c.order_id, c.is_late,
           (SELECT COUNT(*) FROM orders_clean p
             WHERE p.tailor_id = c.tailor_id AND p.order_date < c.order_date
               AND (p.delivered_date IS NULL OR p.delivered_date > c.order_date)) AS open_orders
    FROM orders_clean c
    WHERE c.delivered_date IS NOT NULL
),
banded AS (
    SELECT is_late, open_orders, NTILE(4) OVER (ORDER BY open_orders) AS band FROM load
)
SELECT printf('Q%d', band) || CASE band WHEN 1 THEN ' (quietest)' WHEN 4 THEN ' (busiest)' ELSE '' END AS workload,
       MIN(open_orders) AS min_open_orders,
       MAX(open_orders) AS max_open_orders,
       COUNT(*) AS delivered,
       ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM banded
GROUP BY band
ORDER BY band;

-- name: Late rate by occasion
-- note: Occasions with a fixed event date (funerals, Christmas, weddings) leave no room for delay. Occasions with a high late rate are where to protect capacity.
-- chart: bar late_pct
SELECT occasion,
       COUNT(*) AS delivered,
       ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM orders_clean
WHERE delivered_date IS NOT NULL
GROUP BY occasion
HAVING COUNT(*) >= 30
ORDER BY late_pct DESC;

-- name: Tailor ranking by late rate
-- note: RANK() orders tailors from most to least late. Read it together with the workload table above before judging anyone, because the busiest tailors tend to be the latest.
-- chart: bar late_pct
WITH per_tailor AS (
    SELECT t.name AS tailor, COUNT(*) AS delivered,
           ROUND(100.0 * AVG(o.is_late), 1) AS late_pct
    FROM orders_clean o
    JOIN tailors t ON t.tailor_id = o.tailor_id
    WHERE o.delivered_date IS NOT NULL
    GROUP BY t.tailor_id
)
SELECT tailor, delivered, late_pct,
       RANK() OVER (ORDER BY late_pct DESC) AS worst_rank
FROM per_tailor
ORDER BY worst_rank;

-- name: In-progress orders already past their promised date
-- note: These customers are already waiting. Call them first, then use the ML page to see which of the remaining open orders are likely to follow.
WITH asof AS (SELECT MAX(order_date) AS d FROM orders_clean)
SELECT o.order_id, t.name AS tailor, o.garment_type, o.promised_date,
       CAST(julianday((SELECT d FROM asof)) - julianday(o.promised_date) AS INTEGER) AS days_overdue
FROM orders_clean o
JOIN tailors t ON t.tailor_id = o.tailor_id
WHERE o.delivered_date IS NULL AND o.promised_date < (SELECT d FROM asof)
ORDER BY days_overdue DESC
LIMIT 15;