"""One-time script: normalize existing user skills and recompute profile embeddings.

Run with:
    python scripts/normalize_user_skills.py

This applies alias resolution (e.g. "ReactJS" -> "react", "ML" -> "machine learning")
to all existing user_profiles.skills arrays and recomputes profile embeddings.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import UserProfile
from app.processing.skills import normalize_user_skills
from app.services.embedding import build_profile_text, generate_embedding


def main():
    db = SessionLocal()
    try:
        profiles = db.query(UserProfile).all()
        updated = 0
        for profile in profiles:
            if not profile.skills:
                continue

            original = list(profile.skills)
            normalized = normalize_user_skills(original)

            if normalized != original:
                profile.skills = normalized
                # Recompute embedding with normalized skills
                text = build_profile_text(
                    headline=profile.headline,
                    skills=profile.skills,
                    career_interests=profile.career_interests,
                    experience_level=profile.experience_level,
                )
                profile.profile_embedding = generate_embedding(text, is_query=True)
                updated += 1
                print(f"  Updated: {original} -> {normalized}")

        db.commit()
        print(f"\nDone. {updated}/{len(profiles)} profiles updated.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
