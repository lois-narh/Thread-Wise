import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from app.services import auth, usecases, workspace
from scripts.generate_data import generate


def fmt(v):
    """Number for a KPI tile: 1,234 or 12.5."""
    if pd.isna(v):
        return "-"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def tiles(df):
    """One metric tile per column of a one-row result."""
    for col, (label, value) in zip(st.columns(len(df.columns)), df.iloc[0].items()):
        col.metric(label, fmt(value))


def show_results(results, show_sql=True):
    """Each query: title, what it means, chart, table, and (optionally) the SQL behind it."""
    for r in results:
        st.markdown(f"**{r['name']}**")
        if r["note"]:
            st.caption(r["note"])
        if r["chart"]:
            kind, cols = r["chart"]
            chart = st.bar_chart if kind == "bar" else st.line_chart
            chart(r["df"], x=r["df"].columns[0], y=cols)
        st.dataframe(r["df"], hide_index=True)
        if show_sql:  # expanders cannot be nested, so callers inside an expander pass show_sql=False
            with st.expander("Show SQL"):
                st.code(r["sql"], language="sql")


st.set_page_config(page_title="ThreadWise", page_icon="🧵", layout="wide")
user = st.session_state.get("user")

if not user:
    st.title("🧵 ThreadWise")
    st.write("Welcome, Login to Get Started.")
    login_tab, signup_tab = st.tabs(["Log in", "Create account"])

    with login_tab:
        with st.form("login"):
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary"):
                user, err = auth.login(email, pw)
                if err:
                    st.error(err)
                else:
                    st.session_state["user"] = user
                    st.rerun()

    with signup_tab:
        with st.form("signup"):
            business = st.text_input("Business name")
            name = st.text_input("Your name")
            email = st.text_input("Email")
            pw = st.text_input("Password (8+ characters)", type="password")
            if st.form_submit_button("Create account", type="primary"):
                user, err = auth.signup(name, business, email, pw)
                if err:
                    st.error(err)
                else:
                    st.session_state["user"] = user
                    st.rerun()
else:
    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()
    st.title(f"{user['business']}")
    st.caption(f"Signed in as {user['name']} ({user['email']})")

    has_data = workspace.table_counts(user).get("orders", 0) > 0
    with st.expander("Load data", expanded=not has_data):
        if has_data:
            st.success("Loaded: " + ", ".join(f"{n:,} {t}" for t, n in workspace.table_counts(user).items()))
        n_orders = st.slider("Number of orders", 500, 5000, 2500, 500)
        seed = st.number_input("Seed (same seed = same data)", value=42, step=1)
        if st.button("Generate synthetic data", type="primary"):
            with st.spinner("Generating..."):
                generate(workspace.db_path(user), n_orders, int(seed))
            st.rerun()

    if not has_data:
        st.info("Generate some data to get started.")
        st.stop()

    overview_tab, insights_tab = st.tabs(["Overview", "Insights"])

    # Overview: the plain business numbers
    with overview_tab:
        overview = workspace.run_sql_file(user, "overview.sql")
        tiles(overview[0]["df"])
        show_results(overview[1:])

    # Insights: pick a business problem, see the SQL analysis (model and AI come next)
    with insights_tab:
        options = usecases.all_usecases()
        if not options:
            st.error("No business problems found. Put the .json files in app/usecases/.")
            st.stop()
        keys = list(options)
        saved = workspace.get_usecase(user)
        choice = st.selectbox("Business problem", keys, format_func=lambda k: options[k]["name"],
                              index=keys.index(saved) if saved in keys else 0)
        if choice != saved:
            workspace.set_usecase(user, choice)
        uc = options[choice]
        st.write(uc["description"])
        st.caption(f"Task: {uc['task']} · Target: {uc['target']} · Metrics: {', '.join(uc['metrics'])}")

        tiles(workspace.run_sql_file(user, uc["kpi_sql"])[0]["df"])
        st.markdown("#### Findings")
        show_results(workspace.run_sql_file(user, uc["analysis_sql"]))
        with st.expander("Data quality checks"):
            show_results(workspace.run_sql_file(user, "quality.sql"), show_sql=False)
        st.info("Next: train the model.")