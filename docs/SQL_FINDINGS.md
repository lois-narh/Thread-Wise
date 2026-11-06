# SQL findings
Generated 2026-11-06 from `4219cee190.db` by `scripts/sql_findings.py`. Overall late rate on delivered orders: **43.1%**.

## 1. Data quality
**Question:** How dirty is the raw data, and what does the cleaning view remove?

```sql
SELECT (SELECT COUNT(*) FROM orders) AS raw_rows,
       (SELECT COUNT(*) FROM orders_clean) AS clean_rows,
       (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM orders) AS duplicate_order_ids,
       (SELECT COUNT(*) FROM orders WHERE promised_date < order_date OR delivered_date < order_date) AS impossible_dates,
       (SELECT COUNT(*) FROM orders WHERE deposit_ghs IS NULL) AS missing_deposit,
       (SELECT COUNT(*) FROM orders WHERE price_ghs IS NULL OR price_ghs NOT BETWEEN 1 AND 20000) AS bad_price,
       (SELECT COUNT(*) FROM orders WHERE garment_type IS NULL OR TRIM(garment_type) = '') AS missing_garment
```

| raw_rows | clean_rows | duplicate_order_ids | impossible_dates | missing_deposit | bad_price | missing_garment |
|---|---|---|---|---|---|---|
| 1530 | 1497 | 30 | 3 | 56 | 33 | 29 |

**What it means:** 33 of 1530 raw rows were dropped by `orders_clean` (duplicates and impossible dates). Missing deposits (56) and bad prices (33) are kept but blanked, so they cannot distort averages or model training.

## 2. Late rate by month (conditional aggregation)
**Question:** Is there a season when orders run late?

```sql
SELECT CAST(strftime('%m', order_date) AS INTEGER) AS month,
       COUNT(*) AS delivered,
       ROUND(100.0 * SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS late_pct
FROM orders_clean WHERE delivered_date IS NOT NULL
GROUP BY month ORDER BY month
```

| month | delivered | late_pct |
|---|---|---|
| 1 | 75 | 26.7 |
| 2 | 106 | 33.0 |
| 3 | 162 | 60.5 |
| 4 | 133 | 51.1 |
| 5 | 136 | 39.7 |
| 6 | 132 | 41.7 |
| 7 | 123 | 32.5 |
| 8 | 126 | 31.7 |
| 9 | 161 | 36.0 |
| 10 | 108 | 35.2 |
| 11 | 111 | 56.8 |
| 12 | 106 | 64.2 |

**What it means:** Orders placed in December are late 64.2% of the time, against 43.1% overall (106 orders). Plan capacity and staffing for that month before it starts.

## 3. Late rate by deposit paid
**Question:** Do customers who pay little upfront get their orders late more often?

```sql
SELECT CASE WHEN deposit_pct < 20 THEN '1) under 20%' WHEN deposit_pct < 50 THEN '2) 20-50%' ELSE '3) 50%+' END AS deposit,
       COUNT(*) AS delivered, ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM orders_clean WHERE delivered_date IS NOT NULL AND deposit_pct IS NOT NULL
GROUP BY deposit ORDER BY deposit
```

| deposit | delivered | late_pct |
|---|---|---|
| 1) under 20% | 99 | 45.5 |
| 2) 20-50% | 519 | 44.7 |
| 3) 50%+ | 778 | 41.5 |

**What it means:** The late rate for deposits under 20% compared with 50%+ is higher (45.5% vs 41.5%). A deposit often pays for fabric and trims, so a minimum deposit is a cheap lever to test.

## 4. Late rate by tailor workload (CTE, window function, correlated subquery)
**Question:** Do orders go late when the tailor already has many open orders? `tailor_open_orders` counts the tailor's open orders on the day the order was placed; `band` 1 is the least busy quarter, 4 the busiest.

```sql
WITH f AS (-- One row per order, built on the existing orders_clean view.
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
ORDER BY c.order_date, c.order_id),
banded AS (SELECT is_late, tailor_open_orders, NTILE(4) OVER (ORDER BY tailor_open_orders) AS band
           FROM f WHERE split = 'train')
SELECT band, MIN(tailor_open_orders) AS min_open, MAX(tailor_open_orders) AS max_open,
       COUNT(*) AS delivered, ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM banded GROUP BY band ORDER BY band
```

| band | min_open | max_open | delivered | late_pct |
|---|---|---|---|---|
| 1 | 0 | 1 | 370 | 29.7 |
| 2 | 1 | 2 | 370 | 31.6 |
| 3 | 2 | 3 | 370 | 39.5 |
| 4 | 3 | 10 | 369 | 71.5 |

**What it means:** For the busiest quarter (3+ open orders), the late rate compared with the quietest quarter is higher (71.5% vs 29.7%). This is the main operational lever: cap how many open orders one tailor can carry.

## 5. Tailor ranking (CTE + RANK window)
**Question:** Which tailors deliver late most often?

```sql
WITH per_tailor AS (
    SELECT t.name AS tailor, COUNT(*) AS delivered, ROUND(100.0 * AVG(o.is_late), 1) AS late_pct
    FROM orders_clean o JOIN tailors t ON t.tailor_id = o.tailor_id
    WHERE o.delivered_date IS NOT NULL GROUP BY t.tailor_id)
SELECT tailor, delivered, late_pct, RANK() OVER (ORDER BY late_pct DESC) AS worst_rank
FROM per_tailor ORDER BY worst_rank
```

| tailor | delivered | late_pct | worst_rank |
|---|---|---|---|
| Yaw Boateng | 207 | 61.4 | 1 |
| Abena Owusu | 195 | 57.9 | 2 |
| Ama Serwaa | 196 | 43.4 | 3 |
| Kwame Osei | 180 | 43.3 | 4 |
| Nana Yaa Darko | 169 | 36.7 | 5 |
| Ibrahim Musah | 162 | 35.8 | 6 |
| Kofi Mensah | 190 | 31.1 | 7 |
| Efua Appiah | 180 | 30.6 | 8 |

**What it means:** Yaw Boateng has the highest late rate (61.4%) and Efua Appiah the lowest (30.6%). Compare against each tailor's workload before drawing conclusions about skill.

## 6. Late rate by occasion
**Question:** Which occasions are the riskiest?

```sql
SELECT occasion, COUNT(*) AS delivered, ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM orders_clean WHERE delivered_date IS NOT NULL
GROUP BY occasion HAVING COUNT(*) >= 30 ORDER BY late_pct DESC
```

| occasion | delivered | late_pct |
|---|---|---|
| Easter | 44 | 81.8 |
| Eid | 60 | 80.0 |
| Christmas | 71 | 77.5 |
| Funeral | 292 | 67.8 |
| Unknown | 41 | 56.1 |
| Everyday | 322 | 30.4 |
| School | 122 | 29.5 |
| Wedding | 198 | 29.3 |
| Graduation | 52 | 26.9 |
| Church | 277 | 25.6 |

**What it means:** 'Easter' orders are late 81.8% of the time, 'Church' orders 25.6%. Occasion-driven orders have fixed event dates, so lateness costs the most there.

## 7. Open orders right now (subquery)
**Question:** How many orders in progress are already past their promised date?

```sql
SELECT COUNT(*) AS open_orders,
       SUM(CASE WHEN promised_date < (SELECT MAX(order_date) FROM orders_clean) THEN 1 ELSE 0 END) AS already_past_promised_date
FROM orders_clean WHERE delivered_date IS NULL
```

| open_orders | already_past_promised_date |
|---|---|
| 18 | 1 |

**What it means:** 1 of 18 open orders are already late. Call these customers first; the ML page ranks the rest by risk.

*These are associations in the data, not proven causes. The data is synthetic.*