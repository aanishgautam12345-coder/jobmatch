"""Test the Recommendation Agent with a sample user profile.

Creates a demo user + profile (if not exists), runs the agent, and prints
ranked recommendations with full score breakdowns.

Usage:
    python -m scripts.test_recommend
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import *  # noqa: F401,F403
from app.models.user import User, UserProfile
from app.agents.recommendation_agent import RecommendationAgent


# Edit this to test different personas
DEMO_PROFILE = {
    "email": "demo.python.dev@jobmatch.test",
    "full_name": "Demo Candidate",
    "headline": "Backend Python Developer",
    "skills": ["python", "django", "postgresql", "docker", "aws", "rest", "git"],
    "experience_years": 4,
    "experience_level": "mid",
    "preferred_locations": ["Remote", "United Kingdom"],
    "preferred_job_types": ["full-time"],
    "min_salary": 45000.0,
    "salary_currency": "USD",
    "career_interests": "Backend development, cloud infrastructure, scalable APIs",
}


def get_or_create_demo_profile(db) -> UserProfile:
    """Get the demo user's profile, creating it if needed."""
    user = db.query(User).filter(User.email == DEMO_PROFILE["email"]).first()

    if not user:
        user = User(
            id=uuid.uuid4(),
            email=DEMO_PROFILE["email"],
            password_hash="demo-not-a-real-hash",  # Never do this in production
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()

    if not profile:
        profile = UserProfile(
            id=uuid.uuid4(),
            user_id=user.id,
            full_name=DEMO_PROFILE["full_name"],
            headline=DEMO_PROFILE["headline"],
            skills=DEMO_PROFILE["skills"],
            experience_years=DEMO_PROFILE["experience_years"],
            experience_level=DEMO_PROFILE["experience_level"],
            preferred_locations=DEMO_PROFILE["preferred_locations"],
            preferred_job_types=DEMO_PROFILE["preferred_job_types"],
            min_salary=DEMO_PROFILE["min_salary"],
            salary_currency=DEMO_PROFILE["salary_currency"],
            career_interests=DEMO_PROFILE["career_interests"],
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    else:
        # Force refresh so edits to DEMO_PROFILE above take effect on re-run
        profile.headline = DEMO_PROFILE["headline"]
        profile.skills = DEMO_PROFILE["skills"]
        profile.experience_years = DEMO_PROFILE["experience_years"]
        profile.experience_level = DEMO_PROFILE["experience_level"]
        profile.preferred_locations = DEMO_PROFILE["preferred_locations"]
        profile.preferred_job_types = DEMO_PROFILE["preferred_job_types"]
        profile.min_salary = DEMO_PROFILE["min_salary"]
        profile.career_interests = DEMO_PROFILE["career_interests"]
        profile.profile_embedding = None  # Force re-embedding
        db.commit()

    return profile


def print_recommendations(recommendations: list[dict]):
    print(f"\n{'='*75}")
    print(f"  RECOMMENDATIONS ({len(recommendations)} jobs)")
    print(f"{'='*75}")

    if not recommendations:
        print("  No recommendations found — try loosening the profile criteria.")
        return

    for rec in recommendations:
        print(f"\n  #{rec['rank']}  {rec['title']}  —  {rec['match_percentage']}% match")
        print(f"      Company: {rec['company'] or 'N/A'}")
        loc = rec['location_city'] or rec['location_country'] or ('Remote' if rec['remote'] else 'N/A')
        print(f"      Location: {loc}" + (" (Remote)" if rec['remote'] else ""))
        print(f"      Category: {rec['category']}")
        print(f"      Job Type: {rec['job_type'] or 'N/A'}")
        if rec['salary_min'] or rec['salary_max']:
            print(f"      Salary: {rec['salary_min']} - {rec['salary_max']} {rec['salary_currency']}")

        b = rec['breakdown']
        print(f"      Score breakdown:")
        print(f"        Semantic similarity : {b['semantic_similarity']}%")
        print(f"        Skill overlap        : {b['skill_overlap']}%")
        print(f"        Location fit          : {b['location_fit']}%")
        print(f"        Salary fit            : {b['salary_fit']}%")
        print(f"        Experience fit        : {b['experience_fit']}%")
        print(f"        Job type fit          : {b.get('job_type_fit', 'N/A')}%")

        if rec['matching_skills']:
            print(f"      ✓ Matching skills: {', '.join(rec['matching_skills'])}")
        if rec['missing_skills']:
            missing_preview = rec['missing_skills'][:5]
            print(f"      ✗ Missing skills: {', '.join(missing_preview)}"
                  + (" ..." if len(rec['missing_skills']) > 5 else ""))


def main():
    db = SessionLocal()
    try:
        print("\n" + "="*75)
        print("  JobMatch AI — Recommendation Agent Demo")
        print("="*75)
        print(f"  Profile: {DEMO_PROFILE['headline']}")
        print(f"  Skills: {', '.join(DEMO_PROFILE['skills'])}")
        print(f"  Experience: {DEMO_PROFILE['experience_level']} ({DEMO_PROFILE['experience_years']} years)")
        print(f"  Preferred locations: {', '.join(DEMO_PROFILE['preferred_locations'])}")
        print(f"  Min salary: {DEMO_PROFILE['min_salary']} {DEMO_PROFILE['salary_currency']}")

        profile = get_or_create_demo_profile(db)

        agent = RecommendationAgent(db)
        recommendations = agent.recommend(profile, top_n=10)

        print_recommendations(recommendations)

    finally:
        db.close()


if __name__ == "__main__":
    main()