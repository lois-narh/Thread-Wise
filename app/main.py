import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from app.services import auth, usecases, workspace
from scripts.generate_data import generate

MONEY = {c: st.column_config.NumberColumn(format="%.0f") for c in
         ["Price (GHS)", "Deposit (GHS)", "Balance (GHS)", "Total spent (GHS)"]}


# ---------- small helpers ----------
@st.cache_data(show_spinner=False)
def _run(email, filename, version):
    return workspace.run_sql_file({"email": email}, filename)


def sql(user, filename):
    """Run a SQL file (cached until the workspace database changes)."""
    return _run(user["email"], filename, workspace.db_path(user).stat().st_mtime)


def fmt(v):
    """Number for a tile: 1,234 or 12.5 or 1.65M."""
    if pd.isna(v):
        return "-"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.2f}M"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def tiles(df):
    """One number tile per column of a one-row result."""
    for col, (label, value) in zip(st.columns(len(df.columns)), df.iloc[0].items()):
        col.metric(label, fmt(value))


def show(results, show_sql=False, tables=False):
    """Title, what it means, chart, table. Charts hide their table unless tables=True."""
    for r in results:
        st.markdown(f"**{r['name']}**")
        if r["note"]:
            st.caption(r["note"])
        if r["chart"]:
            kind, cols = r["chart"]
            (st.bar_chart if kind == "bar" else st.line_chart)(r["df"], x=r["df"].columns[0], y=cols)
        if tables or not r["chart"]:
            if r["df"].empty:
                st.success("Nothing here right now.")
            else:
                st.dataframe(r["df"], hide_index=True, column_config=MONEY)
        if show_sql:  # expanders cannot be nested, so never use show_sql inside an expander
            with st.expander("Show SQL"):
                st.code(r["sql"], language="sql")


# ----------Side tabs ----------
def overview_tab(user):
    res = sql(user, "overview.sql")
    tiles(res[0]["df"])
    show(res[1:])


def orders_tab(user):
    df = sql(user, "orders.sql")[0]["df"]
    statuses = sorted(df["Status"].unique())
    c1, c2, c3 = st.columns([2, 2, 3])
    picked = c1.multiselect("Status", statuses, default=statuses)
    tailor = c2.selectbox("Tailor", ["All"] + sorted(df["Tailor"].unique()))
    search = c3.text_input("Search customer or order number")
    df = df[df["Status"].isin(picked)]
    if tailor != "All":
        df = df[df["Tailor"] == tailor]
    if search:
        df = df[df["Customer"].str.contains(search, case=False, na=False, regex=False)
                | df["Order"].str.contains(search, case=False, na=False, regex=False)]
    st.caption(f"{len(df):,} orders")
    st.dataframe(df, hide_index=True, column_config=MONEY, height=520)
    st.download_button("Download as CSV", df.to_csv(index=False), "orders.csv", "text/csv")


def pending_tab(user):
    res = sql(user, "pending.sql")
    tiles(res[0]["df"])
    st.caption(res[0]["note"])
    show(res[1:])


def finances_tab(user):
    res = sql(user, "finances.sql")
    tiles(res[0]["df"])
    st.caption(res[0]["note"])
    show(res[1:])


def insights_tab(user):
    options = usecases.all_usecases()
    if not options:
        st.error(f"No business problems found. Put late_delivery.json and demand_forecast.json in: {usecases.DIR}")
        return
    keys = list(options)
    saved = workspace.get_usecase(user)
    choice = st.selectbox("Business problem", keys, format_func=lambda k: options[k]["name"],
                          index=keys.index(saved) if saved in keys else 0)
    if choice != saved:
        workspace.set_usecase(user, choice)
    uc = options[choice]
    st.write(uc["description"])
    st.caption(f"Task: {uc['task']} · Target: {uc['target']} · Metrics: {', '.join(uc['metrics'])}")

    tiles(sql(user, uc["kpi_sql"])[0]["df"])
    st.markdown("#### Findings")
    show(sql(user, uc["analysis_sql"]), show_sql=True, tables=True)
    with st.expander("Data quality checks"):
        show(sql(user, "quality.sql"), tables=True)
    st.info("Next: train the model.")


# ---------- Auth page ----------
st.set_page_config(page_title="ThreadWise", page_icon="🧵")
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
    st.title(user["business"])
    st.caption(f"Signed in as {user['name']} ({user['email']})")

    counts = workspace.table_counts(user)
    has_data = counts.get("orders", 0) > 0
    with st.expander("Load data", expanded=not has_data):
        if has_data:
            st.success("Loaded: " + ", ".join(f"{n:,} {t}" for t, n in counts.items()))
        n_orders = st.slider("Number of orders", 500, 5000, 2500, 500)
        seed = st.number_input("Seed (same seed = same data)", value=42, step=1)
        if st.button("Generate synthetic data", type="primary"):
            with st.spinner("Generating..."):
                generate(workspace.db_path(user), n_orders, int(seed))
            st.rerun()

    if not has_data:
        st.info("Generate some data to get started.")
        st.stop()

    tabs = st.tabs(["Overview", "Orders", "Pending", "Finances", "Insights"])
    for tab, render in zip(tabs, [overview_tab, orders_tab, pending_tab, finances_tab, insights_tab]):
        with tab:
            render(user)