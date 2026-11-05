-- name: Rows kept after cleaning
-- note: The raw ledger is never edited. The orders_clean view (sql/clean.sql) removes duplicates and impossible rows.
SELECT (SELECT COUNT(*) FROM orders) AS raw_rows,
       (SELECT COUNT(*) FROM orders_clean) AS clean_rows,
       (SELECT COUNT(*) FROM orders) - (SELECT COUNT(*) FROM orders_clean) AS removed;

-- name: Missing values
-- note: Gaps in the ledger. Text gaps become 'Unknown'; numeric gaps are filled with the median when the model is trained.
SELECT COUNT(*) AS orders,
       SUM(CASE WHEN garment_type  IS NULL OR TRIM(garment_type)  = '' THEN 1 ELSE 0 END) AS missing_garment,
       SUM(CASE WHEN occasion      IS NULL OR TRIM(occasion)      = '' THEN 1 ELSE 0 END) AS missing_occasion,
       SUM(CASE WHEN fabric_source IS NULL OR TRIM(fabric_source) = '' THEN 1 ELSE 0 END) AS missing_fabric_source,
       SUM(CASE WHEN complexity    IS NULL THEN 1 ELSE 0 END) AS missing_complexity,
       SUM(CASE WHEN price_ghs     IS NULL THEN 1 ELSE 0 END) AS missing_price,
       SUM(CASE WHEN deposit_ghs   IS NULL THEN 1 ELSE 0 END) AS missing_deposit
FROM orders;

-- name: Duplicate order IDs
-- note: The same order entered twice inflates demand and revenue. Only the first entry is kept.
WITH dupes AS (
    SELECT order_id, COUNT(*) AS entries FROM orders GROUP BY order_id HAVING COUNT(*) > 1
)
SELECT COUNT(*) AS order_ids_duplicated, COALESCE(SUM(entries - 1), 0) AS extra_rows FROM dupes;

-- name: Inconsistent spellings
-- note: Different ways of writing the same thing ("kaba and slit", "KABA & SLIT") would split one garment into several groups.
SELECT 'garment_type' AS field, COUNT(DISTINCT garment_type) AS spellings_in_raw,
       (SELECT COUNT(DISTINCT garment_type) FROM orders_clean) AS values_after_cleaning FROM orders
UNION ALL
SELECT 'occasion', COUNT(DISTINCT occasion), (SELECT COUNT(DISTINCT occasion) FROM orders_clean) FROM orders
UNION ALL
SELECT 'fabric_source', COUNT(DISTINCT fabric_source), (SELECT COUNT(DISTINCT fabric_source) FROM orders_clean) FROM orders;

-- name: Impossible values
-- note: Data-entry slips. Impossible dates drop the row; impossible prices are blanked.
SELECT SUM(CASE WHEN delivered_date < order_date THEN 1 ELSE 0 END) AS delivered_before_ordered,
       SUM(CASE WHEN promised_date  < order_date THEN 1 ELSE 0 END) AS promised_before_ordered,
       SUM(CASE WHEN price_ghs <= 0 OR price_ghs > 20000 THEN 1 ELSE 0 END) AS price_out_of_range,
       SUM(CASE WHEN deposit_ghs > price_ghs THEN 1 ELSE 0 END) AS deposit_above_price
FROM orders;