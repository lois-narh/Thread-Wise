# %% [markdown]
# # ThreadWise: late-order analysis
# End-to-end walk-through on one workspace: SQL features, data quality, patterns, the ML model,
# drift monitoring and the Snwolley summary. It calls the same code the app uses
# (`sql/features_late.sql`, `ml/pipeline.py`, `ai/`), so results match the app.

# %%
import sqlite3
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))
DB = sorted((ROOT / "data" / "workspaces").glob("*.db"))[0]      # first workspace database
SQL = ROOT / "sql" / "features_late.sql"
print("Using", DB.name)

# %% [markdown]
# ## 1. Features from SQL
# One row per order. `tailor_open_orders` is a correlated subquery (how many orders the tailor already had open
# on the day the order was placed), `customer_prior_orders` is a window function, and everything reads from the
# `orders_clean` view, which removes duplicates and impossible records.

# %%
from ml.pipeline import load_dataset

df = load_dataset(DB, SQL)
print(df.shape)
print(df["split"].value_counts().to_string())
df.head()

# %% [markdown]
# ## 2. Data quality
# Raw table versus the cleaned view.

# %%
con = sqlite3.connect(DB)
pd.read_sql_query("""
SELECT (SELECT COUNT(*) FROM orders) AS raw_rows,
       (SELECT COUNT(*) FROM orders_clean) AS clean_rows,
       (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM orders) AS duplicate_order_ids,
       (SELECT COUNT(*) FROM orders WHERE promised_date < order_date OR delivered_date < order_date) AS impossible_dates,
       (SELECT COUNT(*) FROM orders WHERE deposit_ghs IS NULL) AS missing_deposit""", con)

# %% [markdown]
# ## 3. What is associated with late orders?

# %%
done = df[df["split"] == "train"].copy()
print(f"Overall late rate: {done['is_late'].mean():.1%} of {len(done):,} delivered orders")
fig, ax = plt.subplots(1, 3, figsize=(15, 3.5))
(done.groupby("order_month")["is_late"].mean() * 100).plot.bar(ax=ax[0], color="#1E2A4A", title="By month placed")
dep = pd.cut(done["deposit_pct"], [-0.01, 20, 50, 100.01], labels=["<20%", "20-50%", "50%+"])
(done.groupby(dep, observed=True)["is_late"].mean() * 100).plot.bar(ax=ax[1], color="#1E2A4A", title="By deposit paid")
load = pd.qcut(done["tailor_open_orders"], 4, duplicates="drop")
(done.groupby(load, observed=True)["is_late"].mean() * 100).plot.bar(ax=ax[2], color="#1E2A4A", title="By tailor's open orders")
for a in ax:
    a.set_ylabel("% late"); a.tick_params(axis="x", rotation=0)
plt.tight_layout()

# %% [markdown]
# ## 4. The model
# `ml/pipeline.py` does the preprocessing (impute, scale, one-hot), trains a baseline, logistic regression and
# gradient boosting, tests them on the **most recent 20%** of delivered orders (a time split, so the model never
# sees the future), then retrains the winner on all delivered orders and scores the open ones.

# %%
from ml.pipeline import run

ml = run(DB, SQL, ROOT / "ml" / "artifacts" / DB.stem)
print("Best model:", ml["best_model"])
pd.DataFrame(ml["metrics"]).T

# %% [markdown]
# **How to read this.** ROC-AUC 0.5 means no skill; the baseline just guesses the overall late rate.
# `top20pct_capture` is the share of all late orders found among the 20% of orders flagged riskiest, which is the
# number that matters for a shop owner with limited time to chase orders.

# %%
imp = pd.DataFrame(ml["importance"]).head(10).iloc[::-1]
imp.plot.barh(x="feature", y="importance", legend=False, color="#1E2A4A", title="What drives late orders (permutation importance)")
plt.xlabel("Drop in ROC-AUC when the feature is scrambled")
plt.tight_layout()

# %%
risk = pd.DataFrame(ml["predictions"])
risk["drivers"] = risk["drivers"].apply(lambda d: "; ".join(f"{x['feature']}={x['value']} (+{x['risk_points']})" for x in d))
print(risk["risk"].value_counts().to_string())
risk.head(10)

# %% [markdown]
# **Limitations.** The test period has no December, so the December effect is learned but not validated.
# The data is synthetic and its late-order patterns were planted, so this proves the pipeline works, not that
# a real shop will look the same.

# %% [markdown]
# ## 5. Monitoring: has the data drifted?
# Population Stability Index compares each feature's recent distribution with the training period.
# Rule of thumb: under 0.1 stable, 0.1 to 0.25 watch, over 0.25 retrain.

# %%
def psi(old, new, bins=10):
    edges = np.unique(np.quantile(old.dropna(), np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    a = np.histogram(old.dropna(), edges)[0] / old.notna().sum() + 1e-6
    b = np.histogram(new.dropna().clip(edges[0], edges[-1]), edges)[0] / new.notna().sum() + 1e-6
    return float(np.sum((b - a) * np.log(b / a)))

ordered = done.sort_values("order_date")
cut = int(len(ordered) * 0.7)
old, new = ordered.iloc[:cut], ordered.iloc[cut:]
nums = [c for c in ml["features"] if pd.api.types.is_numeric_dtype(done[c])]
pd.DataFrame({"psi": {c: round(psi(old[c], new[c]), 3) for c in nums}}).sort_values("psi", ascending=False)

# %% [markdown]
# In production this check would run on a schedule against each new batch of orders, alongside a running
# ROC-AUC computed as real outcomes arrive. Either one crossing its threshold triggers a retrain.

# %% [markdown]
# ## 6. Snwolley: turn the numbers into advice
# The agent only sees aggregated facts and open-order details (never customer names or phones). Any figure in
# its answer that is not in those facts is flagged.

# %%
from ai.context import build_facts
from ai import insights
from ai.snwolley import AIError

facts = build_facts(str(DB), df, ml, "Demo workspace")
try:
    res = insights.get_insight("executive_summary", facts, ROOT / "ml" / "artifacts" / DB.stem / "ai_cache")
    print(res["text"])
    print("\nFigures not found in the data we sent:", res["unverified_figures"] or "none")
except AIError as e:
    print("AI not available:", e)