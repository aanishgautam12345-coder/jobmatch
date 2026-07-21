"""Test the RAG Explanation Engine.

Runs the Recommendation Agent, then generates a grounded explanation for
each top result using Groq — the "why this job" feature.

Usage:
    python -m scripts.test_explain
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import *  # noqa: F401,F403
from app.models.job import Job, JobSkill
from app.agents.recommendation_agent import RecommendationAgent
from app.services.recommendation import compute_match_score
from app.services.rag import generate_explanation
from scripts.test_recommend import get_or_create_demo_profile, DEMO_PROFILE


def main():
    db = SessionLocal()
    try:
        print("\n" + "="*75)
        print("  JobMatch AI — RAG Explanation Engine Demo")
        print("="*75)

        profile = get_or_create_demo_profile(db)

        agent = RecommendationAgent(db)
        recommendations = agent.recommend(profile, top_n=3)  # Just top 3 for the demo

        if not recommendations:
            print("No recommendations found.")
            return

        print(f"\nGenerating explanations for top {len(recommendations)} recommendations ...")
        print("(This calls the Groq API — needs GROQ_API_KEY in your .env)\n")

        for rec in recommendations:
            job = db.query(Job).filter(Job.id == rec["job_id"]).first()
            job_skills = [s.skill for s in db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]

            # Recompute the breakdown (cheap — no embedding call needed here
            # since we already have the semantic_similarity from the agent's ranking)
            similarity = rec["breakdown"]["semantic_similarity"] / 100
            breakdown = compute_match_score(profile, job, job_skills, similarity)

            explanation = generate_explanation(profile, job, breakdown)

            print(f"{'='*75}")
            print(f"  #{rec['rank']}  {rec['title']}  —  {rec['match_percentage']}% match")
            print(f"  {job.company or 'N/A'}")
            print(f"{'='*75}")
            print(f"  💬 {explanation}")
            print()

    finally:
        db.close()


if __name__ == "__main__":
    main()
