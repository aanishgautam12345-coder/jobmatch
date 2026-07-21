"""JobMatch AI — Streamlit Dashboard.

Run with:
    streamlit run dashboard/app.py

This gives you a working visual interface over everything the backend
already does: semantic search, recommendations, and RAG explanations.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from app.database import SessionLocal
from app.models import *  # noqa: F401,F403

st.set_page_config(
    page_title="JobMatch AI",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Session state ──
if "db" not in st.session_state:
    st.session_state.db = SessionLocal()


# ── Sidebar navigation ──
st.sidebar.title("🎯 JobMatch AI")
st.sidebar.caption("AI-Powered Job Aggregator & Recommendation System")

page = st.sidebar.radio(
    "Navigate",
    ["🏠 Overview", "🔍 Search Jobs", "👤 My Profile", "✨ Recommendations",
     "💾 Saved Jobs", "🆕 Recently Added", "📊 Compare Search Methods"],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.caption("Dissertation Project · JobMatch AI")
st.sidebar.caption("Backend: FastAPI + PostgreSQL + pgvector")
st.sidebar.caption("AI: sentence-transformers + OpenAI")


# ── Route to the right page ──
if page == "🏠 Overview":
    from dashboard.pages import overview
    overview.render(st.session_state.db)

elif page == "🔍 Search Jobs":
    from dashboard.pages import search
    search.render(st.session_state.db)

elif page == "👤 My Profile":
    from dashboard.pages import profile
    profile.render(st.session_state.db)

elif page == "✨ Recommendations":
    from dashboard.pages import recommendations
    recommendations.render(st.session_state.db)

elif page == "💾 Saved Jobs":
    from dashboard.pages import saved
    saved.render(st.session_state.db)

elif page == "🆕 Recently Added":
    from dashboard.pages import recent
    recent.render(st.session_state.db)

elif page == "📊 Compare Search Methods":
    from dashboard.pages import compare
    compare.render(st.session_state.db)
