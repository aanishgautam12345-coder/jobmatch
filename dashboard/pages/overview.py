"""Overview Page — dataset statistics at a glance."""

import streamlit as st
import pandas as pd
from sqlalchemy import func

from app.models.job import Job, JobSkill, RawJob


def render(db):
    st.title("🏠 System Overview")
    st.caption("Live statistics from your job database")

    # ── Top-line metrics ──
    total_jobs = db.query(Job).count()
    total_raw = db.query(RawJob).count()
    jobs_with_embeddings = db.query(Job).filter(Job.embedding.isnot(None)).count()
    jobs_with_skills = db.query(func.count(func.distinct(JobSkill.job_id))).scalar()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Clean Jobs", f"{total_jobs:,}")
    col2.metric("Raw Ingested", f"{total_raw:,}")
    col3.metric("With Embeddings", f"{jobs_with_embeddings:,}")
    col4.metric("With Skills Tagged", f"{jobs_with_skills:,}")

    st.divider()

    col_left, col_right = st.columns(2)

    # ── Category breakdown ──
    with col_left:
        st.subheader("Jobs by Category")
        category_data = (
            db.query(Job.category, func.count(Job.id).label("count"))
            .group_by(Job.category)
            .order_by(func.count(Job.id).desc())
            .all()
        )
        if category_data:
            df = pd.DataFrame(category_data, columns=["Category", "Count"])
            st.bar_chart(df.set_index("Category"))
        else:
            st.info("No jobs processed yet.")

    # ── Source breakdown ──
    with col_right:
        st.subheader("Jobs by Source")
        source_data = (
            db.query(Job.source, func.count(Job.id).label("count"))
            .group_by(Job.source)
            .order_by(func.count(Job.id).desc())
            .all()
        )
        if source_data:
            df = pd.DataFrame(source_data, columns=["Source", "Count"])
            st.bar_chart(df.set_index("Source"))
        else:
            st.info("No jobs processed yet.")

    st.divider()

    # ── Remote vs on-site ──
    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.subheader("Remote vs On-site")
        remote_count = db.query(Job).filter(Job.remote.is_(True)).count()
        onsite_count = total_jobs - remote_count
        df = pd.DataFrame({
            "Type": ["Remote", "On-site"],
            "Count": [remote_count, onsite_count],
        })
        st.bar_chart(df.set_index("Type"))

    with col_right2:
        st.subheader("Jobs with Salary Disclosed")
        with_salary = db.query(Job).filter(
            (Job.salary_min.isnot(None)) | (Job.salary_max.isnot(None))
        ).count()
        without_salary = total_jobs - with_salary
        df = pd.DataFrame({
            "Type": ["Disclosed", "Not Disclosed"],
            "Count": [with_salary, without_salary],
        })
        st.bar_chart(df.set_index("Type"))

    st.divider()
    st.caption(
        "This system aggregates jobs from three sources — CSV dataset, Adzuna API, "
        "and We Work Remotely (scraper) — then cleans, deduplicates, and embeds them "
        "for semantic search and AI-powered recommendations."
    )
