-- One row per order, built on the existing orders_clean view.
-- split: 'train' (delivered, label known) | 'score' (still in progress)
WITH o AS (
    SELECT * FROM orders_clean
),
load AS (                                   -- how many orders the tailor already had open
    SELECT c.order_id,                      -- on the day this order was placed
           (SELECT COUNT(*) FROM o p
             WHERE p.tailor_id = c.tailor_id
               AND p.order_date < c.order_date
               AND (p.delivered_date IS NULL OR p.delivered_date > c.order_date)) AS open_orders
    FROM o c
)
SELECT c.order_id, c.order_date, c.promised_date, c.tailor_id,
       CASE WHEN c.delivered_date IS NULL THEN 'score' ELSE 'train' END AS split,
       c.is_late,
       l.open_orders AS tailor_open_orders,
       COALESCE(t.skill_level, 'Unknown') AS tailor_skill, t.years_experience AS tailor_years,
       c.garment_type, c.fabric_source, c.occasion, c.complexity, c.is_rush, c.lead_days,
       CAST(strftime('%m', c.order_date) AS INTEGER) AS order_month,
       CASE WHEN strftime('%m', c.order_date) = '12' THEN 1 ELSE 0 END AS is_december,
       c.deposit_pct, c.price_ghs,
       COUNT(*) OVER (PARTITION BY c.customer_id ORDER BY c.order_date, c.order_id
                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS customer_prior_orders
FROM o c
JOIN load l ON l.order_id = c.order_id
LEFT JOIN tailors t ON t.tailor_id = c.tailor_id
ORDER BY c.order_date, c.order_id;