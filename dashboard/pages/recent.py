"""Recently Added Jobs Page — shows the latest jobs in the database."""

import streamlit as st

from app.models.job import Job


def render(db):
    st.title("🆕 Recently Added Jobs")
    st.caption("The latest jobs ingested into the system")

    limit = st.slider("How many to show", 10, 50, 20)

    jobs = (
        db.query(Job)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .all()
    )

    if not jobs:
        st.info("No jobs in the database yet.")
        return

    st.success(f"Showing {len(jobs)} most recent jobs")

    for job in jobs:
        with st.container(border=True):
            col_main, col_meta = st.columns([4, 1])

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

            with col_meta:
                st.caption(f"Source: `{job.source}`")
                if job.created_at:
                    st.caption(job.created_at.strftime("%Y-%m-%d"))
