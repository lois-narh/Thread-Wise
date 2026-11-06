"""Turn data + model output into a small, anonymised facts dict for the AI.

Only aggregates and open-order attributes go out. Customer names and phones are
never read here, so they cannot leak into a prompt.
"""
import math
import sqlite3

import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _rate(df):
    return None if df.empty else round(float(df["is_late"].mean()) * 100, 1)


def _by(done, bins):
    return {str(k): _rate(g) for k, g in done.groupby(bins, observed=True) if len(g)}


def _workload_bins(s):
    q = pd.qcut(s, 4, duplicates="drop")
    labels = {iv: (f"{math.floor(iv.left) + 1}-{int(iv.right)} open orders"
                   if math.floor(iv.left) + 1 < int(iv.right) else f"{int(iv.right)} open orders")
              for iv in q.cat.categories}
    return q.map(labels).astype(pd.CategoricalDtype(list(labels.values()), ordered=True))


def build_facts(db_path, features_df: pd.DataFrame, ml: dict, business: str, top_n: int = 8) -> dict:
    df = features_df
    done = df[df["split"] == "train"]
    pend = pd.DataFrame(ml["predictions"])
    as_of = str(df["order_date"].max())
    with sqlite3.connect(db_path) as con:
        tailors = pd.read_sql_query("SELECT tailor_id, name FROM tailors", con).set_index("tailor_id")["name"]
    delivered_value = done["price_ghs"].sum()                       # no payments table in this schema
    sc = df[df["split"] == "score"]
    deposits_held = (sc["price_ghs"] * sc["deposit_pct"] / 100).sum()

    by_month = {MONTHS[m - 1]: _rate(g) for m, g in done.groupby("order_month")}
    by_deposit = _by(done, pd.cut(done["deposit_pct"], [-0.01, 20, 50, 100.01],
                                  labels=["under 20%", "20-50%", "50%+"]))
    by_load = _by(done, _workload_bins(done["tailor_open_orders"]))
    by_occasion = {k: _rate(g) for k, g in done.groupby("occasion") if len(g) >= 30}

    top_orders = []
    for p in ml["predictions"][:top_n]:
        top_orders.append({
            "order_id": p["order_id"], "tailor": tailors.get(p["tailor_id"], "unknown"),
            "promised_date": p["promised_date"], "late_probability_pct": round(p["probability"] * 100),
            "risk": p["risk"],
            "reasons": [f"{d['feature']}={d['value']} (+{d['risk_points']} pts)" for d in p["drivers"]]})
    best = ml["best_model"]
    n_pend = len(pend)
    return {
        "business": business, "data_as_of": as_of,
        "kpis": {"orders_analysed": int(len(done) + n_pend), "completed_orders": int(len(done)),
                 "open_orders": int(n_pend), "late_rate_pct": _rate(done),
                 "delivered_orders_value_ghs": round(float(delivered_value), 2),
                 "deposits_held_on_open_orders_ghs": round(float(deposits_held), 2)},
        "late_rate_pct_by_order_month": by_month,
        "late_rate_pct_by_deposit_share": by_deposit,
        "late_rate_pct_by_tailor_open_orders_at_order_time": by_load,
        "late_rate_pct_by_occasion": by_occasion,
        "model": {"type": best, "roc_auc": ml["metrics"][best]["roc_auc"],
                  "baseline_roc_auc": ml["metrics"]["baseline_base_rate"]["roc_auc"],
                  "top20pct_flagged_captures_late_pct": round(ml["metrics"][best]["top20pct_capture"] * 100)},
        "top_drivers": ml["importance"][:5],
        "open_orders_risk": {
            "high": int((pend["risk"] == "high").sum()) if n_pend else 0,
            "medium": int((pend["risk"] == "medium").sum()) if n_pend else 0,
            "already_past_promised_date": int((pend["promised_date"] < as_of).sum()) if n_pend else 0,
            "highest_risk_orders": top_orders},
        "data_note": "Duplicates and impossible records were removed before analysis.",
    }