import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from app.services import auth, usecases, workspace
from scripts.generate_data import generate


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
    st.title(f"The {user['business']} Dashboard")
    st.write(f"Signed in as {user['name']} ({user['email']}).")

    # Step 1: data
    st.subheader("1. Your data")
    counts = workspace.table_counts(user)
    if counts:
        st.success("Loaded: " + ", ".join(f"{n:,} {t}" for t, n in counts.items()))
        st.dataframe(workspace.preview(user), hide_index=True)
    with st.expander("Generate synthetic data", expanded=not counts):
        n_orders = st.slider("Number of orders", 500, 5000, 2500, 500)
        seed = st.number_input("Seed (same seed = same data)", value=42, step=1)
        if st.button("Generate data", type="primary"):
            with st.spinner("Generating..."):
                generate(workspace.db_path(user), n_orders, int(seed))
            st.rerun()
 
    # Step 2: business problem
    st.subheader("2. What do you want to solve?")
    if not counts:
        st.caption("Load your data first.")
    else:
        options = usecases.all_usecases()
        keys = list(options)
        saved = workspace.get_usecase(user)
        choice = st.selectbox("Business problem", keys, format_func=lambda k: options[k]["name"],
                              index=keys.index(saved) if saved in keys else 0)
        uc = options[choice]
        st.write(uc["description"])
        st.caption(f"Task: {uc['task']} · Target: {uc['target']} · Metrics: {', '.join(uc['metrics'])}")
        if st.button("Use this problem", type="primary"):
            workspace.set_usecase(user, choice)
            st.rerun()
        if saved == choice:
            st.success(f"Selected: {uc['name']}")
            st.info("Next: SQL analysis.")
 