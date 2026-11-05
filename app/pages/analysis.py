"""Analysis page. Streamlit adds any file in app/pages/ to the sidebar automatically."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))          # so `app`, `ml`, `ai` can be imported

import streamlit as st

from app.views import insights

st.set_page_config(page_title="Analysis - ThreadWise", layout="wide")

user = st.session_state.get("user")
if not user:
    st.warning("Please log in first (go to the main page).")
    st.stop()

insights.render(
    db_path=ROOT / "data" / "workspaces" / "demo" / "business.db",
    business=user.get("business", "Your business"),
    out_dir=str(ROOT / "ml" / "artifacts" / "demo"),
    sql_path=str(ROOT / "sql" / "features_late.sql"),
)