"""Run the analysis queries on a workspace database and write docs/SQL_FINDINGS.md.

Usage (from project root):  python scripts/sql_findings.py [path/to/workspace.db]
Every number in the output comes from the database, so the findings always match the data.
"""
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted((ROOT / "data" / "workspaces").glob("*.db"))[0]
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
con = sqlite3.connect(DB)
DONE = "delivered_date IS NOT NULL"


def q(sql):
    return pd.read_sql_query(sql, con)


def table(df):
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns)
    rows = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head] + rows)


def vs(a, b, what):
    """'X is higher/lower than Y' in words, computed from the numbers."""
    if abs(a - b) < 1:
        return f"{what} is about the same ({a}% vs {b}%)"
    return f"{what} is {'higher' if a > b else 'lower'} ({a}% vs {b}%)"


overall = float(q(f"SELECT ROUND(100.0*AVG(is_late),1) AS v FROM orders_clean WHERE {DONE}")["v"][0])
out = [f"# SQL findings", f"Generated {date.today()} from `{DB.name}` by `scripts/sql_findings.py`. "
       f"Overall late rate on delivered orders: **{overall}%**.", ""]


def section(title, question, sql, df, meaning):
    out.extend([f"## {title}", f"**Question:** {question}", "", "```sql", sql.strip(), "```", "", table(df), "",
                f"**What it means:** {meaning}", ""])


# 1. data quality ---------------------------------------------------------------
sql = """
SELECT (SELECT COUNT(*) FROM orders) AS raw_rows,
       (SELECT COUNT(*) FROM orders_clean) AS clean_rows,
       (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM orders) AS duplicate_order_ids,
       (SELECT COUNT(*) FROM orders WHERE promised_date < order_date OR delivered_date < order_date) AS impossible_dates,
       (SELECT COUNT(*) FROM orders WHERE deposit_ghs IS NULL) AS missing_deposit,
       (SELECT COUNT(*) FROM orders WHERE price_ghs IS NULL OR price_ghs NOT BETWEEN 1 AND 20000) AS bad_price,
       (SELECT COUNT(*) FROM orders WHERE garment_type IS NULL OR TRIM(garment_type) = '') AS missing_garment"""
df = q(sql); r = df.iloc[0]
section("1. Data quality", "How dirty is the raw data, and what does the cleaning view remove?", sql, df,
        f"{int(r.raw_rows - r.clean_rows)} of {int(r.raw_rows)} raw rows were dropped by `orders_clean` "
        f"(duplicates and impossible dates). Missing deposits ({int(r.missing_deposit)}) and bad prices "
        f"({int(r.bad_price)}) are kept but blanked, so they cannot distort averages or model training.")

# 2. month (conditional aggregation) -------------------------------------------
sql = f"""
SELECT CAST(strftime('%m', order_date) AS INTEGER) AS month,
       COUNT(*) AS delivered,
       ROUND(100.0 * SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS late_pct
FROM orders_clean WHERE {DONE}
GROUP BY month ORDER BY month"""
df = q(sql); top = df[df["delivered"] >= 50].sort_values("late_pct", ascending=False).iloc[0]
section("2. Late rate by month (conditional aggregation)", "Is there a season when orders run late?", sql, df,
        f"Orders placed in {MONTHS[int(top.month)]} are late {top.late_pct}% of the time, against {overall}% overall "
        f"({int(top.delivered)} orders). Plan capacity and staffing for that month before it starts.")

# 3. deposit ---------------------------------------------------------------------
sql = f"""
SELECT CASE WHEN deposit_pct < 20 THEN '1) under 20%' WHEN deposit_pct < 50 THEN '2) 20-50%' ELSE '3) 50%+' END AS deposit,
       COUNT(*) AS delivered, ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM orders_clean WHERE {DONE} AND deposit_pct IS NOT NULL
GROUP BY deposit ORDER BY deposit"""
df = q(sql)
section("3. Late rate by deposit paid", "Do customers who pay little upfront get their orders late more often?", sql, df,
        vs(df.late_pct.iloc[0], df.late_pct.iloc[-1], "The late rate for deposits under 20% compared with 50%+") +
        ". A deposit often pays for fabric and trims, so a minimum deposit is a cheap lever to test.")

# 4. workload (CTE + window function NTILE, on the model's feature query) --------
features = (ROOT / "sql" / "features_late.sql").read_text().strip().rstrip(";")
sql = f"""
WITH f AS ({features}),
banded AS (SELECT is_late, tailor_open_orders, NTILE(4) OVER (ORDER BY tailor_open_orders) AS band
           FROM f WHERE split = 'train')
SELECT band, MIN(tailor_open_orders) AS min_open, MAX(tailor_open_orders) AS max_open,
       COUNT(*) AS delivered, ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM banded GROUP BY band ORDER BY band"""
df = q(sql)
section("4. Late rate by tailor workload (CTE, window function, correlated subquery)",
        "Do orders go late when the tailor already has many open orders? `tailor_open_orders` counts the "
        "tailor's open orders on the day the order was placed; `band` 1 is the least busy quarter, 4 the busiest.",
        sql, df,
        vs(df.late_pct.iloc[-1], df.late_pct.iloc[0], f"For the busiest quarter ({int(df.min_open.iloc[-1])}+ open orders), the late rate compared with the quietest quarter") +
        ". This is the main operational lever: cap how many open orders one tailor can carry.")

# 5. tailors (CTE + RANK) --------------------------------------------------------
sql = f"""
WITH per_tailor AS (
    SELECT t.name AS tailor, COUNT(*) AS delivered, ROUND(100.0 * AVG(o.is_late), 1) AS late_pct
    FROM orders_clean o JOIN tailors t ON t.tailor_id = o.tailor_id
    WHERE o.{DONE} GROUP BY t.tailor_id)
SELECT tailor, delivered, late_pct, RANK() OVER (ORDER BY late_pct DESC) AS worst_rank
FROM per_tailor ORDER BY worst_rank"""
df = q(sql)
section("5. Tailor ranking (CTE + RANK window)", "Which tailors deliver late most often?", sql, df,
        f"{df.tailor.iloc[0]} has the highest late rate ({df.late_pct.iloc[0]}%) and {df.tailor.iloc[-1]} the lowest "
        f"({df.late_pct.iloc[-1]}%). Compare against each tailor's workload before drawing conclusions about skill.")

# 6. occasion --------------------------------------------------------------------
sql = f"""
SELECT occasion, COUNT(*) AS delivered, ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM orders_clean WHERE {DONE}
GROUP BY occasion HAVING COUNT(*) >= 30 ORDER BY late_pct DESC"""
df = q(sql)
section("6. Late rate by occasion", "Which occasions are the riskiest?", sql, df,
        f"'{df.occasion.iloc[0]}' orders are late {df.late_pct.iloc[0]}% of the time, "
        f"'{df.occasion.iloc[-1]}' orders {df.late_pct.iloc[-1]}%. Occasion-driven orders have fixed event dates, so lateness costs the most there.")

# 7. open orders ------------------------------------------------------------------
sql = """
SELECT COUNT(*) AS open_orders,
       SUM(CASE WHEN promised_date < (SELECT MAX(order_date) FROM orders_clean) THEN 1 ELSE 0 END) AS already_past_promised_date
FROM orders_clean WHERE delivered_date IS NULL"""
df = q(sql)
section("7. Open orders right now (subquery)", "How many orders in progress are already past their promised date?", sql, df,
        f"{int(df.already_past_promised_date.iloc[0])} of {int(df.open_orders.iloc[0])} open orders are already late. "
        "Call these customers first; the ML page ranks the rest by risk.")

out.append("*These are associations in the data, not proven causes. The data is synthetic.*")
dest = ROOT / "docs" / "SQL_FINDINGS.md"
dest.parent.mkdir(exist_ok=True)
dest.write_text("\n".join(out), encoding="utf-8")
print("Wrote", dest)