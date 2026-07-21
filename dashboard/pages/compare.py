"""Compare Page — semantic search vs keyword search, side by side.

This IS your dissertation's core research demonstration: does Agentic AI +
semantic search outperform traditional keyword-based job search?
"""

import streamlit as st

from app.services.search import semantic_search, keyword_search


def render(db):
    st.title("📊 Semantic vs Keyword Search")
    st.caption(
        "This is your dissertation's core comparison — see it live. "
        "Semantic search ranks by meaning; keyword search matches literal words."
    )

    query = st.text_input(
        "Enter a search query to compare",
        placeholder="e.g. entry level marketing no experience",
    )

    limit = st.slider("Results per method", 3, 10, 5)

    if st.button("⚖️ Compare", type="primary") or query:
        if not query:
            st.warning("Enter a query above.")
            return

        with st.spinner("Running both search methods ..."):
            semantic_results = semantic_search(db, query=query, limit=limit)
            keyword_results = keyword_search(db, query=query, limit=limit)

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("🧠 Semantic Search (AI)")
            st.caption(f"{len(semantic_results)} results — ranked by meaning")
            _render_results(semantic_results, show_match=True)

        with col_right:
            st.subheader("🔤 Keyword Search (Baseline)")
            st.caption(f"{len(keyword_results)} results — literal word matching")
            _render_results(keyword_results, show_match=False)

        st.divider()
        st.markdown(
            "**For your evaluation chapter:** manually label which results above are "
            "genuinely relevant to the query, then compute Precision@k for each method. "
            "Repeat across several queries covering different vocabulary gaps to build "
            "your results table."
        )


def _render_results(results: list[dict], show_match: bool):
    if not results:
        st.info("No results.")
        return

    for job in results:
        with st.container(border=True):
            st.markdown(f"**{job['title']}**")
            st.caption(job.get("company") or "N/A")
            loc = job.get("location_city") or job.get("location_country") or "N/A"
            remote = " 🌍" if job.get("remote") else ""
            st.write(f"📍 {loc}{remote}  ·  {job.get('category', 'N/A')}")
            if show_match and "match_percentage" in job:
                st.caption(f"Match: {job['match_percentage']}%")
