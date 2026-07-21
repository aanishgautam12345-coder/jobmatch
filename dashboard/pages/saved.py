"""Saved Jobs Page — view and manage saved jobs."""

import uuid
import streamlit as st

from app.models.job import Job
from app.models.recommendation import SavedJob
from dashboard.pages.profile import get_or_create_user


def render(db):
    st.title("💾 Saved Jobs")
    st.caption("Jobs you've saved for later")

    user = get_or_create_user(db)

    saved = (
        db.query(SavedJob, Job)
        .join(Job, Job.id == SavedJob.job_id)
        .filter(SavedJob.user_id == user.id)
        .order_by(SavedJob.saved_at.desc())
        .all()
    )

    if not saved:
        st.info("You haven't saved any jobs yet. Save jobs from the Recommendations or Search pages.")
        return

    st.success(f"{len(saved)} saved job(s)")

    for saved_record, job in saved:
        with st.container(border=True):
            col_main, col_action = st.columns([4, 1])

            with col_main:
                st.markdown(f"**{job.title_clean or job.title}**")
                st.caption(job.company or "N/A")
                loc = job.location_city or job.location_country or "N/A"
                remote = " 🌍 Remote" if job.remote else ""
                st.write(f"📍 {loc}{remote}  ·  🏷️ {job.category or 'N/A'}")

                if job.salary_min or job.salary_max:
                    smin, smax = job.salary_min, job.salary_max
                    currency = job.salary_currency or ""
                    st.write(f"💰 {smin:,.0f} - {smax:,.0f} {currency}" if smin
                             else f"💰 Up to {smax:,.0f} {currency}")

                if job.url:
                    st.markdown(f"[View original posting]({job.url})")

                st.caption(f"Saved on: {saved_record.saved_at.strftime('%Y-%m-%d %H:%M')}")

            with col_action:
                if st.button("🗑️ Remove", key=f"unsave_{job.id}"):
                    db.delete(saved_record)
                    db.commit()
                    st.rerun()
