"""Profile Page — create and edit the user's profile.

For simplicity (no full auth UI yet), this uses a single demo user
identified by session state. In the full system, this would be tied
to a logged-in user via the Auth module.
"""

import uuid
import streamlit as st

from app.models.user import User, UserProfile
from app.services.embedding import build_profile_text, generate_embedding


DEMO_EMAIL = "dashboard.user@jobmatch.test"


def get_or_create_user(db) -> User:
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if not user:
        user = User(id=uuid.uuid4(), email=DEMO_EMAIL, password_hash="dashboard-demo")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_or_create_profile(db, user_id) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(id=uuid.uuid4(), user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def render(db):
    st.title("👤 My Profile")
    st.caption("This profile powers your personalised recommendations")

    user = get_or_create_user(db)
    profile = get_or_create_profile(db, user.id)

    with st.form("profile_form"):
        col1, col2 = st.columns(2)

        with col1:
            full_name = st.text_input("Full name", value=profile.full_name or "")
            headline = st.text_input(
                "Headline",
                value=profile.headline or "",
                placeholder="e.g. Backend Python Developer",
            )
            experience_level = st.selectbox(
                "Experience level",
                ["junior", "mid", "senior", "lead", "principal"],
                index=["junior", "mid", "senior", "lead", "principal"].index(
                    profile.experience_level
                ) if profile.experience_level in ["junior", "mid", "senior", "lead", "principal"] else 1,
            )
            experience_years = st.number_input(
                "Years of experience", min_value=0, max_value=50,
                value=profile.experience_years or 0,
            )

        with col2:
            skills_text = st.text_area(
                "Skills (comma-separated)",
                value=", ".join(profile.skills) if profile.skills else "",
                placeholder="python, django, postgresql, docker, aws",
                height=100,
            )
            locations_text = st.text_input(
                "Preferred locations (comma-separated)",
                value=", ".join(profile.preferred_locations) if profile.preferred_locations else "",
                placeholder="Remote, United Kingdom",
            )
            min_salary = st.number_input(
                "Minimum salary expectation",
                min_value=0.0, value=profile.min_salary or 0.0, step=1000.0,
            )
            salary_currency = st.selectbox(
                "Currency", ["USD", "GBP", "EUR", "INR", "AUD", "CAD"],
                index=["USD", "GBP", "EUR", "INR", "AUD", "CAD"].index(
                    profile.salary_currency
                ) if profile.salary_currency in ["USD", "GBP", "EUR", "INR", "AUD", "CAD"] else 0,
            )

        career_interests = st.text_area(
            "Career interests / what you're looking for",
            value=profile.career_interests or "",
            placeholder="e.g. Backend development, cloud infrastructure, scalable APIs",
        )

        submitted = st.form_submit_button("💾 Save Profile", type="primary")

    if submitted:
        skills_list = [s.strip() for s in skills_text.split(",") if s.strip()]
        locations_list = [l.strip() for l in locations_text.split(",") if l.strip()]

        profile.full_name = full_name or None
        profile.headline = headline or None
        profile.experience_level = experience_level
        profile.experience_years = int(experience_years)
        profile.skills = skills_list
        profile.preferred_locations = locations_list
        profile.min_salary = min_salary if min_salary > 0 else None
        profile.salary_currency = salary_currency
        profile.career_interests = career_interests or None

        # Recompute the embedding — this is what powers matching
        with st.spinner("Updating your profile embedding ..."):
            text = build_profile_text(
                headline=profile.headline,
                skills=profile.skills,
                career_interests=profile.career_interests,
                experience_level=profile.experience_level,
            )
            profile.profile_embedding = generate_embedding(text)

        db.commit()
        st.success("✓ Profile saved and re-embedded! Head to Recommendations to see your matches.")

    st.divider()
    if profile.skills:
        st.subheader("Current skills")
        st.write(" · ".join(f"`{s}`" for s in profile.skills))
