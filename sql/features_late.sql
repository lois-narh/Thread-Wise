-- One row per order, cleaned, with features known at order time.
-- split: 'train' (completed, trusted label) | 'score' (still open) | 'exclude'
WITH base AS (
    SELECT o.*, ROW_NUMBER() OVER (
        PARTITION BY customer_id, tailor_id, garment_type_id, order_date, promised_date, total_price
        ORDER BY order_id) AS rn                      -- rn > 1 = duplicate entry
    FROM orders o
),
clean AS (
    SELECT order_id, customer_id, tailor_id, garment_type_id, order_date, promised_date,
           LOWER(TRIM(status)) AS status,             -- 'Completed' -> 'completed'
           CASE WHEN completed_date < order_date THEN NULL ELSE completed_date END AS completed_date,
           CASE WHEN completed_date < order_date THEN 1 ELSE 0 END AS bad_dates,
           total_price, deposit_paid, is_rush, fabric_from, fittings_requested
    FROM base WHERE rn = 1
),
load AS (                                             -- workload when the order was placed
    SELECT c.order_id,
           (SELECT COUNT(*) FROM clean p
             WHERE p.tailor_id = c.tailor_id AND p.order_id < c.order_id
               AND p.order_date <= c.order_date AND p.status <> 'cancelled' AND p.bad_dates = 0
               AND (p.completed_date IS NULL OR p.completed_date > c.order_date)) AS open_orders
    FROM clean c
)
SELECT c.order_id, c.order_date, c.promised_date, c.tailor_id,
       CASE WHEN c.bad_dates = 1 THEN 'exclude'
            WHEN c.status = 'completed' THEN 'train'
            WHEN c.status = 'in_progress' THEN 'score'
            ELSE 'exclude' END AS split,
       CASE WHEN c.status = 'completed' AND c.bad_dates = 0
            THEN CASE WHEN c.completed_date > c.promised_date THEN 1 ELSE 0 END END AS is_late,
       l.open_orders AS tailor_open_orders,
       ROUND(1.0 * l.open_orders / t.weekly_capacity, 2) AS load_ratio,
       t.skill_level,
       g.name AS garment, g.complexity,
       c.is_rush, c.fabric_from, c.fittings_requested,
       CAST(julianday(c.promised_date) - julianday(c.order_date) AS INTEGER) AS promised_days,
       CAST(strftime('%m', c.order_date) AS INTEGER) AS order_month,
       CASE WHEN strftime('%m', c.order_date) = '12' THEN 1 ELSE 0 END AS is_december,
       ROUND(c.deposit_paid / c.total_price, 3) AS deposit_ratio,   -- NULL if deposit missing
       c.total_price,
       COUNT(*) OVER (PARTITION BY c.customer_id ORDER BY c.order_id
                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS customer_prior_orders
FROM clean c
JOIN load l           ON l.order_id = c.order_id
JOIN tailors t        ON t.tailor_id = c.tailor_id
JOIN garment_types g  ON g.garment_type_id = c.garment_type_id
ORDER BY c.order_id;