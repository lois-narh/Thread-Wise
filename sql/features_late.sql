-- One row per order, cleaned, with features that were known when the order was placed.
-- split: 'train' (delivered, trusted label) | 'score' (still in progress) | 'exclude'
-- Works on the tables written by scripts/generate_data.py: orders, tailors.
WITH ranked AS (                                     -- the same order can be entered twice with the same order_id
    SELECT o.*, ROW_NUMBER() OVER (PARTITION BY o.order_id ORDER BY o.rowid) AS rn
    FROM orders o
),
clean AS (
    SELECT r.order_id, r.customer_id, r.tailor_id, r.order_date, r.promised_date,
           LOWER(TRIM(r.status)) AS status,
           CASE WHEN r.delivered_date < r.order_date THEN NULL ELSE r.delivered_date END AS delivered_date,
           CASE WHEN r.delivered_date < r.order_date THEN 1 ELSE 0 END AS bad_dates,   -- delivered before ordered
           COALESCE(CASE
               WHEN LOWER(TRIM(r.garment_type)) LIKE 'kaba%'    THEN 'Kaba & Slit'
               WHEN LOWER(TRIM(r.garment_type)) LIKE 'agbada%'  THEN 'Agbada'
               WHEN LOWER(TRIM(r.garment_type)) LIKE 'suit%'    THEN 'Suit'
               WHEN LOWER(TRIM(r.garment_type)) LIKE 'bridal%'  THEN 'Bridal Gown'
               WHEN LOWER(TRIM(r.garment_type)) LIKE '%uniform%' THEN 'School Uniform'
               WHEN LOWER(TRIM(r.garment_type)) LIKE 'ankara%'  THEN 'Ankara Two-piece'
               WHEN LOWER(TRIM(r.garment_type)) LIKE '%shirt%'  THEN 'Shirt'
               WHEN LOWER(TRIM(r.garment_type)) LIKE 'dress%'   THEN 'Dress'
           END, 'unknown') AS garment,
           COALESCE(LOWER(TRIM(r.fabric_source)), 'unknown') AS fabric,
           COALESCE(LOWER(TRIM(r.occasion)), 'unknown')      AS occasion,
           r.complexity, r.is_rush,
           CASE WHEN r.price_ghs > 10000 THEN NULL ELSE r.price_ghs END AS price_ghs,  -- extra zeros typed
           r.deposit_ghs
    FROM ranked r
    WHERE r.rn = 1
),
flagged AS (
    SELECT c.*,
           CASE WHEN c.status = 'delivered' AND c.delivered_date IS NOT NULL THEN 1 ELSE 0 END AS is_closed
    FROM clean c
),
load AS (                                            -- how many jobs the tailor still had open when this order came in
    SELECT c.order_id,
           (SELECT COUNT(*) FROM flagged p
             WHERE p.tailor_id = c.tailor_id
               AND (p.order_date < c.order_date OR (p.order_date = c.order_date AND p.order_id < c.order_id))
               AND p.bad_dates = 0 AND p.status <> 'cancelled'
               AND (p.delivered_date IS NULL OR p.delivered_date > c.order_date)) AS open_orders,
           -- how often this customer's earlier orders were already known to be late on that day
           (SELECT AVG(CASE WHEN p.delivered_date > p.promised_date THEN 1.0 ELSE 0.0 END) FROM flagged p
             WHERE p.customer_id = c.customer_id AND p.is_closed = 1
               AND p.delivered_date <= c.order_date) AS customer_past_late_rate
    FROM flagged c
)
SELECT f.order_id, f.order_date, f.promised_date, f.tailor_id,
       CASE WHEN f.bad_dates = 1 THEN 'exclude'
            WHEN f.is_closed = 1 THEN 'train'
            WHEN f.status IN ('in progress', 'in_progress') THEN 'score'
            ELSE 'exclude' END AS split,
       CASE WHEN f.is_closed = 1 AND f.bad_dates = 0
            THEN CASE WHEN f.delivered_date > f.promised_date THEN 1 ELSE 0 END END AS is_late,
       l.open_orders                                              AS tailor_open_orders,
       COALESCE(t.skill_level, 'unknown')                         AS skill_level,
       t.years_experience,
       f.garment, f.fabric, f.occasion, f.complexity, f.is_rush,
       CAST(julianday(f.promised_date) - julianday(f.order_date) AS INTEGER) AS promised_days,
       CAST(strftime('%m', f.order_date) AS INTEGER)              AS order_month,
       ROUND(f.deposit_ghs / f.price_ghs, 3)                      AS deposit_ratio,   -- NULL if either is missing
       f.price_ghs,
       COUNT(*) OVER (PARTITION BY f.customer_id ORDER BY f.order_date, f.order_id
                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS customer_prior_orders,
       l.customer_past_late_rate
FROM flagged f
JOIN load l           ON l.order_id = f.order_id
LEFT JOIN tailors t   ON t.tailor_id = f.tailor_id
ORDER BY f.order_date, f.order_id;