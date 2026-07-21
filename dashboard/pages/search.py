"""Search Page — semantic job search interface."""

import streamlit as st

from app.services.search import semantic_search, hybrid_search
from app.processing.category import CATEGORIES


def render(db):
    st.title("🔍 Semantic Job Search")
    st.caption("Search by meaning, not just keywords — powered by vector embeddings")

    query = st.text_input(
        "What are you looking for?",
        placeholder="e.g. remote python developer, senior data scientist, entry level marketing",
    )

    with st.expander("Advanced filters"):
        col1, col2, col3 = st.columns(3)
        with col1:
            country = st.text_input("Country", placeholder="e.g. United Kingdom")
        with col2:
            category = st.selectbox("Category", ["Any"] + CATEGORIES)
        with col3:
            remote_only = st.checkbox("Remote only")

    limit = st.slider("Number of results", 5, 30, 10)

    if st.button("🔎 Search", type="primary") or query:
        if not query:
            st.warning("Enter a search query above.")
            return

        with st.spinner("Searching by meaning ..."):
            if country or category != "Any" or remote_only:
                results = hybrid_search(
                    db, query=query,
                    location_country=country or None,
                    remote_only=remote_only,
                    category=None if category == "Any" else category,
                    limit=limit,
                )
            else:
                results = semantic_search(db, query=query, limit=limit)

        if not results:
            st.info("No matching jobs found. Try a broader query.")
            return

        st.success(f"Found {len(results)} matches")

        for job in results:
            with st.container(border=True):
                col_main, col_score = st.columns([4, 1])

                with col_main:
                    st.markdown(f"**{job['title']}**")
                    st.caption(f"{job.get('company') or 'N/A'}")

                    loc = job.get("location_city") or job.get("location_country") or "N/A"
                    remote_tag = " 🌍 Remote" if job.get("remote") else ""
                    st.write(f"📍 {loc}{remote_tag}  ·  🏷️ {job.get('category', 'N/A')}")

                    if job.get("salary_min") or job.get("salary_max"):
                        smin = job.get("salary_min")
                        smax = job.get("salary_max")
                        currency = job.get("salary_currency", "")
                        if smin:
                            st.write(f"💰 {smin:,.0f} - {smax:,.0f} {currency}")
                        else:
                            st.write(f"💰 Up to {smax:,.0f} {currency}")

                    if job.get("url"):
                        st.markdown(f"[View original posting]({job['url']})")

                with col_score:
                    if "match_percentage" in job:
                        st.metric("Match", f"{job['match_percentage']}%")
