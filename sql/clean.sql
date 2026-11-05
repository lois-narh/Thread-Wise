-- orders_clean: the one cleaned view every analysis and model reads from.
-- Fixes: duplicate ledger entries, inconsistent spellings, impossible values, impossible dates.
DROP VIEW IF EXISTS orders_clean;
CREATE VIEW orders_clean AS
WITH std AS (
    SELECT order_id, customer_id, tailor_id, order_date, promised_date, delivered_date, status,
        CASE WHEN garment_type IS NULL OR TRIM(garment_type) = '' THEN 'Unknown'
             WHEN LOWER(garment_type) LIKE 'kaba%'    THEN 'Kaba & Slit'
             WHEN LOWER(garment_type) LIKE 'agbada%'  THEN 'Agbada'
             WHEN LOWER(garment_type) LIKE 'suit%'    THEN 'Suit'
             WHEN LOWER(garment_type) LIKE 'bridal%'  THEN 'Bridal Gown'
             WHEN LOWER(garment_type) LIKE 'school%'  THEN 'School Uniform'
             WHEN LOWER(garment_type) LIKE 'ankara%'  THEN 'Ankara Two-piece'
             WHEN LOWER(garment_type) LIKE '%shirt%'  THEN 'Shirt'
             WHEN LOWER(garment_type) LIKE 'dress%'   THEN 'Dress'
             ELSE 'Other' END AS garment_type,
        COALESCE(NULLIF(UPPER(SUBSTR(TRIM(fabric_source), 1, 1)) || LOWER(SUBSTR(TRIM(fabric_source), 2)), ''), 'Unknown') AS fabric_source,
        COALESCE(NULLIF(UPPER(SUBSTR(TRIM(occasion), 1, 1)) || LOWER(SUBSTR(TRIM(occasion), 2)), ''), 'Unknown') AS occasion,
        CASE WHEN complexity BETWEEN 1 AND 5 THEN complexity END AS complexity,
        COALESCE(is_rush, 0) AS is_rush,
        CASE WHEN price_ghs BETWEEN 1 AND 20000 THEN price_ghs END AS price_ghs,
        CASE WHEN price_ghs BETWEEN 1 AND 20000 AND deposit_ghs BETWEEN 0 AND price_ghs THEN deposit_ghs END AS deposit_ghs
    FROM orders
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_date) AS rn FROM std
)
SELECT order_id, customer_id, tailor_id, order_date, promised_date, delivered_date, status,
       garment_type, fabric_source, occasion, complexity, is_rush, price_ghs, deposit_ghs,
       CAST(julianday(promised_date) - julianday(order_date) AS INTEGER) AS lead_days,
       ROUND(100.0 * deposit_ghs / price_ghs) AS deposit_pct,
       CASE WHEN delivered_date IS NULL THEN NULL
            WHEN delivered_date > promised_date THEN 1 ELSE 0 END AS is_late,
       CASE WHEN delivered_date IS NULL THEN NULL
            ELSE MAX(0, CAST(julianday(delivered_date) - julianday(promised_date) AS INTEGER)) END AS days_late
FROM ranked
WHERE rn = 1
  AND promised_date >= order_date
  AND (delivered_date IS NULL OR delivered_date >= order_date);