"""Turn data + model output into a small, anonymised facts dict for the AI.

Only aggregates and open-order attributes go out. Customer names, phones and
emails are never read here, so they cannot leak into a prompt.
"""
import sqlite3

import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _rate(df):
    return {} if df.empty else round(float(df["is_late"].mean()) * 100, 1)


def build_facts(db_path, features_df: pd.DataFrame, ml: dict, business: str, top_n: int = 8) -> dict:
    df = features_df
    done = df[df["split"] == "train"]
    pend = pd.DataFrame(ml["predictions"])
    as_of = str(df["order_date"].max())
    with sqlite3.connect(db_path) as con:
        pay = pd.read_sql_query("SELECT order_id, amount FROM payments", con)
        tailors = pd.read_sql_query("SELECT tailor_id, full_name FROM tailors", con).set_index("tailor_id")["full_name"]
    revenue = pay[pay["order_id"].isin(df["order_id"])]["amount"].sum()  # ignore duplicate-order payments

    by_month = {MONTHS[m - 1]: _rate(g) for m, g in done.groupby("order_month")}
    dep = pd.cut(done["deposit_ratio"], [-0.01, 0.2, 0.5, 1.01], labels=["under 20%", "20-50%", "50%+"])
    by_deposit = {str(k): _rate(g) for k, g in done.groupby(dep, observed=True)}
    lb = pd.cut(done["load_ratio"], [-0.01, 0.5, 0.8, 1.0, 99], labels=["<50%", "50-80%", "80-100%", ">100%"])
    by_load = {str(k): _rate(g) for k, g in done.groupby(lb, observed=True)}

    top_orders = []
    for p in ml["predictions"][:top_n]:
        top_orders.append({
            "order_id": p["order_id"], "tailor": tailors.get(p["tailor_id"], "unknown"),
            "promised_date": p["promised_date"], "late_probability_pct": round(p["probability"] * 100),
            "risk": p["risk"],
            "reasons": [f"{d['feature']}={d['value']} (+{d['risk_points']} pts)" for d in p["drivers"]]})
    best = ml["best_model"]
    return {
        "business": business, "data_as_of": as_of,
        "kpis": {"orders_analysed": int(len(done) + len(pend)), "completed_orders": int(len(done)),
                 "open_orders": int(len(pend)), "late_rate_pct": _rate(done),
                 "cash_collected_ghs": round(float(revenue), 2)},
        "late_rate_pct_by_order_month": by_month,
        "late_rate_pct_by_deposit_share": by_deposit,
        "late_rate_pct_by_tailor_workload_vs_capacity": by_load,
        "model": {"type": best, "roc_auc": ml["metrics"][best]["roc_auc"],
                  "baseline_roc_auc": ml["metrics"]["baseline_base_rate"]["roc_auc"],
                  "top20pct_flagged_captures_late_pct": round(ml["metrics"][best]["top20pct_capture"] * 100)},
        "top_drivers": ml["importance"][:5],
        "open_orders_risk": {
            "high": int((pend["risk"] == "high").sum()) if len(pend) else 0,
            "medium": int((pend["risk"] == "medium").sum()) if len(pend) else 0,
            "already_past_promised_date": int((pend["promised_date"] < as_of).sum()) if len(pend) else 0,
            "highest_risk_orders": top_orders},
        "data_note": "Synthetic demo data. Duplicates and impossible dates were removed before analysis.",
    }