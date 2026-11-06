"""ML model, AI insights and Report pages. Each function draws one sidebar page."""
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from ai import insights as ai
from ai.context import MONTHS, build_facts
from ai.snwolley import AIError
from ml.pipeline import load_dataset, run

ROOT = Path(__file__).resolve().parents[1]
SQL = str(ROOT / "sql" / "features_late.sql")
TASKS = {"executive_summary": "Executive summary", "action_plan": "Three actions this week",
         "explain_drivers": "Why orders run late"}


@st.cache_data(show_spinner="Training the model on this workspace's data...")
def _train(db_path: str, data_version: float):
    out = ROOT / "ml" / "artifacts" / Path(db_path).stem        # one folder per workspace
    return run(db_path, SQL, out), load_dataset(db_path, SQL)


def _get(user, db_path):
    """Train (cached) and build the facts the pages and the AI use."""
    p = Path(db_path)
    try:
        ml, df = _train(str(p), p.stat().st_mtime)              # new data -> retrain
    except Exception as e:
        st.error("Could not train the model. Check that data is loaded and sql/features_late.sql matches your tables.")
        st.exception(e)
        st.stop()
    return ml, build_facts(str(p), df, ml, user["business"])


def _bar(data: dict, title: str):
    d = pd.DataFrame({"group": list(data), "late_pct": list(data.values())})
    st.altair_chart(alt.Chart(d).mark_bar(color="#1E2A4A").encode(
        x=alt.X("group:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("late_pct:Q", title="% of orders late"), tooltip=["group", "late_pct"]
    ).properties(title=title, height=260))


def _risk_table(db_path, ml, only=None):
    with sqlite3.connect(db_path) as con:
        names = pd.read_sql_query("SELECT tailor_id, name FROM tailors", con).set_index("tailor_id")["name"]
    rows = [{"Order": p["order_id"], "Tailor": names.get(p["tailor_id"], "?"), "Promised": p["promised_date"],
             "Chance of being late": p["probability"] * 100, "Risk": p["risk"],
             "Why": "; ".join(f"{d['feature'].replace('_', ' ')} = {d['value']}" for d in p["drivers"])}
            for p in ml["predictions"] if only is None or p["risk"] == only]
    return pd.DataFrame(rows)


def _show_risk(df):
    if df.empty:
        st.info("No open orders in this group.")
    else:
        st.dataframe(df, hide_index=True, column_config={"Chance of being late": st.column_config.ProgressColumn(
            format="%.0f%%", min_value=0, max_value=100)})


def _ask(task, facts, db_path, question=None):
    try:
        with st.spinner("Asking the Snwolley agent..."):
            cache = ROOT / "ml" / "artifacts" / Path(db_path).stem / "ai_cache"
            st.session_state.setdefault("ai", {})[task] = ai.get_insight(task, facts, cache, question)
    except AIError as e:
        st.error(str(e))


def _show_ai(res, title):
    st.markdown(f"#### {title}")
    st.write(res["text"])
    if res["unverified_figures"]:
        st.warning("Check these figures before relying on them. They are not in the data we sent: "
                   + ", ".join(res["unverified_figures"]))


# ---------- pages ----------
def ml_page(user, db_path):
    ml, facts = _get(user, db_path)
    best = ml["best_model"]
    m, base = ml["metrics"][best], ml["metrics"]["baseline_base_rate"]
    st.write("**Problem:** predict which open orders will miss their promised date.")
    c = st.columns(4)
    c[0].metric("Best model", best.replace("_", " ").title())
    c[1].metric("ROC-AUC", m["roc_auc"], f"{m['roc_auc'] - base['roc_auc']:+.2f} vs baseline")
    c[2].metric("Late orders caught", f"{m['top20pct_capture'] * 100:.0f}%", help="Share of late orders found "
                "in the 20% of orders the model flags as riskiest")
    c[3].metric("High-risk open orders", facts["open_orders_risk"]["high"])
    st.caption(f"Trained on {ml['n_train']:,} delivered orders and tested on the most recent {ml['n_test']:,}. "
               "The baseline guesses the overall late rate for every order. The test period contains no "
               "December, so the December effect is learned but not validated.")
    with st.expander("All model scores"):
        st.dataframe(pd.DataFrame(ml["metrics"]).T)
    st.markdown("#### What drives late orders")
    imp = pd.DataFrame(ml["importance"]).head(8).iloc[::-1].set_index("feature")
    st.bar_chart(imp, horizontal=True)
    st.markdown("#### Open orders by risk")
    level = st.selectbox("Show", ["high", "medium", "low", "all"])
    _show_risk(_risk_table(db_path, ml, None if level == "all" else level))


def ai_page(user, db_path):
    _, facts = _get(user, db_path)
    st.write("The Snwolley agent reads this workspace's numbers and model results and explains them. "
             "Only totals and open-order details are sent. Customer names and phone numbers never leave the app.")
    cols = st.columns(len(TASKS))
    for col, (task, label) in zip(cols, TASKS.items()):
        if col.button(label):
            _ask(task, facts, db_path)
    q = st.text_input("Or ask your own question about this data")
    if st.button("Ask") and q.strip():
        _ask("ask", facts, db_path, q)
    for task, res in st.session_state.get("ai", {}).items():
        _show_ai(res, TASKS.get(task, "Your question"))


def report_page(user, db_path):
    ml, facts = _get(user, db_path)
    k, ai_state = facts["kpis"], st.session_state.setdefault("ai", {})
    st.caption(f"Data as of {facts['data_as_of']}")
    c = st.columns(4)
    c[0].metric("Delivered orders", f"{k['completed_orders']:,}")
    c[1].metric("Late rate", f"{k['late_rate_pct']}%")
    c[2].metric("Open orders", k["open_orders"])
    c[3].metric("High-risk open orders", facts["open_orders_risk"]["high"])
    months = {m: facts["late_rate_pct_by_order_month"][m] for m in MONTHS if m in facts["late_rate_pct_by_order_month"]}
    _bar(months, "Late rate by month the order was placed")
    a, b = st.columns(2)
    with a: _bar(facts["late_rate_pct_by_deposit_share"], "Late rate by deposit paid")
    with b: _bar(facts["late_rate_pct_by_tailor_open_orders_at_order_time"], "Late rate by tailor's open orders")
    st.markdown("#### Orders most likely to be late")
    _show_risk(_risk_table(db_path, ml, "high").head(10))

    if "executive_summary" not in ai_state and st.button("Write the executive summary with Snwolley", type="primary"):
        _ask("executive_summary", facts, db_path)
    for task in ("executive_summary", "action_plan"):
        if task in ai_state:
            _show_ai(ai_state[task], TASKS[task])
    st.download_button("Download report", _markdown(facts, ai_state), "threadwise_report.md")


def _markdown(facts, ai_state) -> str:
    k, r = facts["kpis"], facts["open_orders_risk"]
    md = [f"# {facts['business']}: late-order report", f"Data as of {facts['data_as_of']}", "", "## Key figures",
          f"- Delivered orders: {k['completed_orders']}", f"- Late rate: {k['late_rate_pct']}%",
          f"- Open orders: {k['open_orders']} ({r['high']} high risk, {r['already_past_promised_date']} already past promised date)",
          f"- Value of delivered orders: GHS {k['delivered_orders_value_ghs']:,.2f}",
          f"- Deposits held on open orders: GHS {k['deposits_held_on_open_orders_ghs']:,.2f}", ""]
    for title, key in (("month the order was placed", "late_rate_pct_by_order_month"),
                       ("deposit paid", "late_rate_pct_by_deposit_share"),
                       ("tailor's open orders", "late_rate_pct_by_tailor_open_orders_at_order_time")):
        md += [f"## Late rate by {title}"] + [f"- {a}: {b}%" for a, b in facts[key].items()] + [""]
    md += ["## Highest-risk open orders"] + [f"- Order {o['order_id']} ({o['tailor']}): {o['late_probability_pct']}% chance, "
           f"due {o['promised_date']}" for o in r["highest_risk_orders"]] + [""]
    for task, res in ai_state.items():
        md += [f"## {TASKS.get(task, 'Answer')}", res["text"], ""]
    return "\n".join(md)