import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from app.services import auth

st.set_page_config(page_title="ThreadWise", page_icon="🧵")
user = st.session_state.get("user")

if not user:
    st.title("🧵 ThreadWise")
    st.write("See which orders will run late before they do, and why.")
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
    st.title(f"👋 {user['business']}")
    st.write(f"Signed in as {user['name']} ({user['email']}).")
    st.info("Next: load data and choose what to predict.")