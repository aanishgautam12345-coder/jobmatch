"""Recommendations Page — runs the Recommendation Agent for the dashboard user."""

import streamlit as st

from app.models.job import Job, JobSkill
from app.agents.recommendation_agent import RecommendationAgent
from app.services.recommendation import compute_match_score
from app.services.rag import generate_explanation
from dashboard.pages.profile import get_or_create_user, get_or_create_profile


def render(db):
    st.title("✨ AI Recommendations")
    st.caption("Ranked by the autonomous Recommendation Agent, based on your profile")

    user = get_or_create_user(db)
    profile = get_or_create_profile(db, user.id)

    if not profile.skills and not profile.headline:
        st.warning("Your profile is empty. Go to **👤 My Profile** and fill it in first.")
        return

    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"**Profile:** {profile.headline or 'No headline set'}")
        if profile.skills:
            st.write("**Skills:** " + ", ".join(profile.skills))
    with col2:
        top_n = st.number_input("Results", min_value=3, max_value=20, value=10)

    if st.button("🚀 Get Recommendations", type="primary"):
        with st.spinner("Agent is retrieving and scoring candidates ..."):
            agent = RecommendationAgent(db)
            recommendations = agent.recommend(profile, top_n=top_n)

        st.session_state["recommendations"] = recommendations

    recommendations = st.session_state.get("recommendations", [])

    if not recommendations:
        st.info("Click **Get Recommendations** to run the agent.")
        return

    st.success(f"{len(recommendations)} recommendations generated")

    for rec in recommendations:
        with st.container(border=True):
            col_main, col_score = st.columns([4, 1])

            with col_main:
                st.markdown(f"**#{rec['rank']} · {rec['title']}**")
                st.caption(rec.get("company") or "N/A")

                loc = rec.get("location_city") or rec.get("location_country") or "N/A"
                remote_tag = " 🌍 Remote" if rec.get("remote") else ""
                st.write(f"📍 {loc}{remote_tag}  ·  🏷️ {rec.get('category', 'N/A')}")

                if rec.get("salary_min") or rec.get("salary_max"):
                    smin, smax = rec.get("salary_min"), rec.get("salary_max")
                    currency = rec.get("salary_currency", "")
                    st.write(f"💰 {smin:,.0f} - {smax:,.0f} {currency}" if smin
                             else f"💰 Up to {smax:,.0f} {currency}")

            with col_score:
                st.metric("Match", f"{rec['match_percentage']}%")

            # Score breakdown
            b = rec["breakdown"]
            bcol1, bcol2, bcol3, bcol4, bcol5 = st.columns(5)
            bcol1.caption(f"Semantic\n**{b['semantic_similarity']}%**")
            bcol2.caption(f"Skills\n**{b['skill_overlap']}%**")
            bcol3.caption(f"Location\n**{b['location_fit']}%**")
            bcol4.caption(f"Salary\n**{b['salary_fit']}%**")
            bcol5.caption(f"Experience\n**{b['experience_fit']}%**")

            if rec.get("matching_skills"):
                st.write("✅ " + ", ".join(rec["matching_skills"]))
            if rec.get("missing_skills"):
                st.write("➕ Consider learning: " + ", ".join(rec["missing_skills"][:5]))

            # RAG explanation on demand — don't call the LLM for every card automatically
            if st.button(f"💬 Why this job?", key=f"explain_{rec['job_id']}"):
                with st.spinner("Generating explanation ..."):
                    job = db.query(Job).filter(Job.id == rec["job_id"]).first()
                    job_skills = [s.skill for s in
                                 db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]
                    similarity = b["semantic_similarity"] / 100
                    breakdown = compute_match_score(profile, job, job_skills, similarity)
                    explanation = generate_explanation(profile, job, breakdown)
                st.info(explanation)

            if rec.get("url"):
                st.markdown(f"[View original posting]({rec['url']})")
