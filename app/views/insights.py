"""Analysis page: KPIs, open-order risk, model results, AI insights, report download."""
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from ai import insights
from ai.context import MONTHS, build_facts
from ai.snwolley import AIError
from ml.pipeline import load_dataset, run

SQL = "sql/features_late.sql"
AI_TASKS = {"executive_summary": "Executive summary", "action_plan": "Three actions this week",
            "explain_drivers": "Why orders run late"}


@st.cache_data(show_spinner="Training the model on your data...")
def _analyse(db_path, sql_path, out_dir):
    return run(db_path, sql_path, out_dir), load_dataset(db_path, sql_path)


def _bar(data: dict, title: str):
    s = pd.DataFrame({"group": list(data), "late_pct": list(data.values())})
    chart = (alt.Chart(s).mark_bar(color="#1E2A4A")
             .encode(x=alt.X("group:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
                     y=alt.Y("late_pct:Q", title="% of orders late"),
                     tooltip=["group", "late_pct"]).properties(title=title, height=260))
    st.altair_chart(chart)


def _report(facts, ai_texts) -> str:
    k = facts["kpis"]
    md = [f"# {facts['business']}: late-order report", f"Data as of {facts['data_as_of']}", "",
          "## Key figures",
          f"- Completed orders: {k['completed_orders']}", f"- Late rate: {k['late_rate_pct']}%",
          f"- Open orders: {k['open_orders']} ({facts['open_orders_risk']['high']} high risk)",
          f"- Cash collected: GHS {k['cash_collected_ghs']:,.2f}", ""]
    for name, d in (("By order month", facts["late_rate_pct_by_order_month"]),
                    ("By deposit share", facts["late_rate_pct_by_deposit_share"]),
                    ("By tailor workload vs capacity", facts["late_rate_pct_by_tailor_workload_vs_capacity"])):
        md += [f"## Late rate {name}"] + [f"- {a}: {b}%" for a, b in d.items()] + [""]
    for task, text in ai_texts.items():
        md += [f"## {AI_TASKS.get(task, 'Answer')}", text, ""]
    return "\n".join(md)


def render(db_path, business, out_dir="ml/artifacts/demo", sql_path=SQL):
    st.title(f"{business}: late-order analysis")
    if st.button("Re-run analysis"):
        st.cache_data.clear()
        st.session_state.pop("ai", None)
        st.rerun()
    try:
        ml, df = _analyse(str(db_path), sql_path, out_dir)
    except Exception as e:                      # show a clear message, keep details in the log
        st.error("The analysis could not run. Check that the workspace has data and the SQL file exists.")
        st.exception(e)
        return
    facts = build_facts(str(db_path), df, ml, business)
    k = facts["kpis"]
    ai_state = st.session_state.setdefault("ai", {})

    t_over, t_risk, t_model, t_ai = st.tabs(["Overview", "Orders at risk", "Model", "AI insights"])

    with t_over:
        c = st.columns(4)
        c[0].metric("Completed orders", f"{k['completed_orders']:,}")
        c[1].metric("Late rate", f"{k['late_rate_pct']}%")
        c[2].metric("Open orders", k["open_orders"])
        c[3].metric("Cash collected", f"GHS {k['cash_collected_ghs']:,.0f}")
        months = {m: facts["late_rate_pct_by_order_month"][m] for m in MONTHS
                  if m in facts["late_rate_pct_by_order_month"]}
        _bar(months, "Late rate by month the order was placed")
        a, b = st.columns(2)
        with a: _bar(facts["late_rate_pct_by_deposit_share"], "Late rate by deposit paid")
        with b: _bar(facts["late_rate_pct_by_tailor_workload_vs_capacity"], "Late rate by tailor workload")

    with t_risk:
        with sqlite3.connect(db_path) as con:
            names = pd.read_sql_query("SELECT tailor_id, full_name FROM tailors", con).set_index("tailor_id")["full_name"]
        rows = [{"Order": p["order_id"], "Tailor": names.get(p["tailor_id"], "?"),
                 "Promised": p["promised_date"], "Chance of being late": p["probability"] * 100,
                 "Risk": p["risk"],
                 "Why": "; ".join(f"{d['feature'].replace('_', ' ')} = {d['value']}" for d in p["drivers"])}
                for p in ml["predictions"]]
        if not rows:
            st.info("No open orders to score.")
        else:
            level = st.selectbox("Show", ["all", "high", "medium", "low"])
            shown = [r for r in rows if level == "all" or r["Risk"] == level]
            st.dataframe(pd.DataFrame(shown), hide_index=True,
                         column_config={"Chance of being late": st.column_config.ProgressColumn(
                             format="%.0f%%", min_value=0, max_value=100)})

    with t_model:
        best = ml["best_model"]
        st.write(f"Best model: **{best.replace('_', ' ')}**. It was tested on the most recent "
                 f"{ml['n_test']} completed orders, which it had not seen during training.")
        st.dataframe(pd.DataFrame(ml["metrics"]).T)
        st.caption("The baseline just guesses the overall late rate for every order (ROC-AUC 0.5 = no skill). "
                   "The test period has no December, so the December effect is learned but not validated.")
        imp = pd.DataFrame(ml["importance"]).head(8).iloc[::-1].set_index("feature")
        st.bar_chart(imp, horizontal=True)

    with t_ai:
        st.caption("Only totals and open-order details are sent to the AI. Customer names and phone numbers never leave this app.")
        cols = st.columns(len(AI_TASKS))
        for col, (task, label) in zip(cols, AI_TASKS.items()):
            if col.button(label):
                _ask(task, facts, out_dir, ai_state)
        q = st.text_input("Or ask your own question about this data")
        if st.button("Ask") and q.strip():
            _ask("ask", facts, out_dir, ai_state, q)
        for task, res in ai_state.items():
            st.subheader(AI_TASKS.get(task, "Your question"))
            st.write(res["text"])
            if res["unverified_figures"]:
                st.warning("Check these figures before relying on them. They are not in the data "
                           f"we sent: {', '.join(res['unverified_figures'])}")
        st.download_button("Download report", _report(facts, {t: r["text"] for t, r in ai_state.items()}),
                           file_name="threadwise_report.md")


def _ask(task, facts, out_dir, state, question=None):
    try:
        with st.spinner("Asking the Snwolley agent..."):
            state[task] = insights.get_insight(task, facts, Path(out_dir) / "ai_cache", question)
    except AIError as e:
        st.error(str(e))