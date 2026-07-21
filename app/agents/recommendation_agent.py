"""Recommendation Agent — the autonomous core of JobMatch AI.

Unlike a static function, this agent DECIDES:
    - how many candidates to retrieve from the vector search
    - whether the candidate pool is strong enough to return
    - how to rank and trim the final recommendation list
    - whether to apply cross-encoder reranking for higher quality

Every decision is logged to the RecommendationRun audit trail for
reproducibility and dissertation analysis.
"""

import json
import logging
import time
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job, JobSkill
from app.models.user import UserProfile
from app.models.recommendation import Recommendation
from app.models.recommendation_run import RecommendationRun
from app.services.embedding import build_profile_text, generate_embedding
from app.services.recommendation import compute_match_score, MatchBreakdown
from app.services.reranker import is_reranker_available, rerank_candidates
from app.services.scoring_config import load_weights

logger = logging.getLogger(__name__)

# Agent behaviour parameters
INITIAL_CANDIDATE_POOL = 30
EXPANDED_CANDIDATE_POOL = 80
QUALITY_THRESHOLD = 0.35
MIN_ACCEPTABLE_SCORE = 0.15
RERANK_THRESHOLD = 20


class RecommendationAgent:
    """Autonomous agent that produces ranked, scored job recommendations
    for a user profile."""

    def __init__(self, db: Session):
        self.db = db

    def recommend(self, profile: UserProfile, top_n: int = 10, hard_constraints: dict | None = None) -> list[dict]:
        """Generate ranked recommendations for a user profile.

        Every step is timed and logged to the RecommendationRun audit trail.
        """
        start_time = time.time()
        weights = load_weights()

        run = RecommendationRun(
            id=uuid.uuid4(),
            user_id=profile.user_id,
            retrieval_method="hnsw_semantic",
            embedding_model="BAAI/bge-base-en-v1.5",
            embedding_dim=768,
            reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2" if is_reranker_available() else None,
            scoring_config={
                "weights_version": weights.version,
                "weights": weights.to_dict(),
                "initial_pool": INITIAL_CANDIDATE_POOL,
                "expanded_pool": EXPANDED_CANDIDATE_POOL,
                "quality_threshold": QUALITY_THRESHOLD,
                "min_acceptable_score": MIN_ACCEPTABLE_SCORE,
                "rerank_threshold": RERANK_THRESHOLD,
                "hard_constraints": hard_constraints,
            },
        )

        decisions: list[dict] = []

        # Step 1 — ensure profile embedding exists
        if profile.profile_embedding is None:
            profile.profile_embedding = self._compute_profile_embedding(profile)
            self.db.commit()
            decisions.append({"step": "compute_embedding", "action": "computed_profile_embedding"})

        # Step 2 — initial retrieval
        candidates, similarities = self._retrieve_candidates(profile, limit=INITIAL_CANDIDATE_POOL)
        run.candidate_pool_size = len(candidates)
        decisions.append({"step": "retrieve", "pool_size": len(candidates), "method": "hnsw_cosine"})

        if not candidates:
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.agent_decisions = {"decisions": decisions}
            run.latency_ms = (time.time() - start_time) * 1000
            self.db.add(run)
            self.db.commit()
            return []

        # Step 3 — score initial pool with hard constraints
        scored = self._score_candidates(profile, candidates, similarities, hard_constraints)
        decisions.append({
            "step": "score",
            "scored_count": len(scored),
            "hard_constraints_applied": hard_constraints is not None,
        })

        # Step 4 — AGENT DECISION: expand pool?
        passing = [s for s in scored if s["breakdown"].passes_hard_filters]
        avg_score = (sum(s["breakdown"].overall_score for s in passing) / len(passing)) if passing else 0.0

        if avg_score < QUALITY_THRESHOLD and len(candidates) < EXPANDED_CANDIDATE_POOL:
            logger.info(
                f"Agent: pool avg {avg_score:.2f} < {QUALITY_THRESHOLD}, "
                f"expanding to {EXPANDED_CANDIDATE_POOL}"
            )
            candidates, similarities = self._retrieve_candidates(profile, limit=EXPANDED_CANDIDATE_POOL)
            scored = self._score_candidates(profile, candidates, similarities, hard_constraints)
            run.candidate_pool_size = len(candidates)
            decisions.append({
                "step": "expand_pool",
                "trigger": "low_avg_score",
                "avg_score": round(avg_score, 4),
                "new_pool_size": len(candidates),
            })
        else:
            decisions.append({
                "step": "pool_quality_check",
                "avg_score": round(avg_score, 4),
                "action": "kept_initial_pool",
            })

        # Step 5 — filter, rerank, rank
        scored = [s for s in scored if s["breakdown"].passes_hard_filters]
        hard_filtered_count = len(scored)
        scored = [s for s in scored if s["breakdown"].overall_score >= MIN_ACCEPTABLE_SCORE]
        decisions.append({
            "step": "filter",
            "after_hard_filter": hard_filtered_count,
            "after_min_score": len(scored),
        })

        # Reranking decision
        if is_reranker_available() and len(scored) > RERANK_THRESHOLD:
            scored = self._rerank_scored(profile, scored)
            run.reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            decisions.append({
                "step": "rerank",
                "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
                "reranked_count": len(scored),
            })
        else:
            decisions.append({
                "step": "rerank",
                "action": "skipped",
                "reason": "pool_too_small" if len(scored) <= RERANK_THRESHOLD else "model_unavailable",
            })

        scored.sort(key=lambda s: s["breakdown"].overall_score, reverse=True)
        final = scored[:top_n]
        run.final_pool_size = len(final)
        run.agent_decisions = {"decisions": decisions}

        # Persist
        self._persist_recommendations(profile, final, run)

        elapsed_ms = (time.time() - start_time) * 1000
        run.latency_ms = round(elapsed_ms, 1)
        run.completed_at = datetime.utcnow()
        self.db.commit()

        return [
            {
                "job_id": str(item["job"].id),
                "title": item["job"].title_clean or item["job"].title,
                "company": item["job"].company,
                "location_city": item["job"].location_city,
                "location_country": item["job"].location_country,
                "remote": item["job"].remote,
                "salary_min": item["job"].salary_min,
                "salary_max": item["job"].salary_max,
                "salary_currency": item["job"].salary_currency,
                "category": item["job"].category,
                "job_type": item["job"].job_type,
                "url": item["job"].url,
                "rank": rank,
                "match_percentage": item["breakdown"].match_percentage,
                "breakdown": {
                    "semantic_similarity": round(item["breakdown"].semantic_similarity * 100, 1),
                    "skill_overlap": round(item["breakdown"].skill_overlap * 100, 1),
                    "location_fit": round(item["breakdown"].location_fit * 100, 1),
                    "salary_fit": round(item["breakdown"].salary_fit * 100, 1),
                    "experience_fit": round(item["breakdown"].experience_fit * 100, 1),
                    "job_type_fit": round(item["breakdown"].job_type_fit * 100, 1),
                },
                "matching_skills": item["breakdown"].matching_skills,
                "missing_skills": item["breakdown"].missing_skills,
                "recommendation_run_id": str(run.id),
            }
            for rank, item in enumerate(final, 1)
        ]

    def _compute_profile_embedding(self, profile: UserProfile) -> list[float]:
        """Turn the user profile into a vector — the same embedding space as jobs."""
        text = build_profile_text(
            headline=profile.headline,
            skills=profile.skills,
            career_interests=profile.career_interests,
            experience_level=profile.experience_level,
        )
        return generate_embedding(text, is_query=True)

    def _retrieve_candidates(self, profile: UserProfile, limit: int) -> tuple[list[Job], list[float]]:
        """Vector search: find the `limit` jobs closest to the profile embedding."""
        distance = Job.embedding.cosine_distance(profile.profile_embedding)

        stmt = (
            select(Job, (1 - distance).label("similarity"))
            .where(Job.embedding.isnot(None))
            .order_by(distance)
            .limit(limit)
        )

        results = self.db.execute(stmt).all()
        jobs = [row[0] for row in results]
        similarities = [float(row[1]) for row in results]

        return jobs, similarities

    def _score_candidates(
        self, profile: UserProfile, candidates: list[Job], similarities: list[float],
        hard_constraints: dict | None = None,
    ) -> list[dict]:
        """Score every candidate job against the profile using pre-computed similarities."""
        results = []

        for job, similarity in zip(candidates, similarities):
            job_skills = [s.skill for s in
                         self.db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]

            breakdown = compute_match_score(
                profile, job, job_skills, similarity,
                profile.preferred_job_types,
                hard_constraints=hard_constraints,
            )

            results.append({"job": job, "breakdown": breakdown})

        return results

    def _rerank_scored(self, profile: UserProfile, scored: list[dict]) -> list[dict]:
        """Apply cross-encoder reranking to scored candidates."""
        query_text = build_profile_text(
            headline=profile.headline,
            skills=profile.skills,
            career_interests=profile.career_interests,
            experience_level=profile.experience_level,
        )

        candidate_dicts = []
        for item in scored:
            job = item["job"]
            candidate_dicts.append({
                "title": job.title_clean or job.title,
                "company": job.company or "",
                "location_city": job.location_city or "",
                "location_country": job.location_country or "",
                "_original_item": item,
            })

        reranked = rerank_candidates(query_text, candidate_dicts, score_field="title")

        results = []
        for cand in reranked:
            item = cand["_original_item"]
            rerank_norm = max(0, min(1, (cand.get("rerank_score", 0) + 10) / 20))
            blended = 0.7 * item["breakdown"].overall_score + 0.3 * rerank_norm
            item["breakdown"].overall_score = blended
            item["breakdown"].match_percentage = round(blended * 100, 1)
            results.append(item)

        return results

    def _persist_recommendations(self, profile: UserProfile, scored: list[dict], run: RecommendationRun):
        """Save recommendations to the database, replacing any previous set."""
        self.db.query(Recommendation).filter(
            Recommendation.user_id == profile.user_id
        ).delete()

        for rank, item in enumerate(scored, 1):
            self.db.add(Recommendation(
                id=uuid.uuid4(),
                user_id=profile.user_id,
                job_id=item["job"].id,
                match_score=item["breakdown"].overall_score,
                rank=rank,
                score_breakdown={
                    "semantic": round(item["breakdown"].semantic_similarity, 4),
                    "skills": round(item["breakdown"].skill_overlap, 4),
                    "location": round(item["breakdown"].location_fit, 4),
                    "salary": round(item["breakdown"].salary_fit, 4),
                    "experience": round(item["breakdown"].experience_fit, 4),
                    "job_type": round(item["breakdown"].job_type_fit, 4),
                },
                retrieval_method="hnsw_semantic",
                candidate_pool_position=rank,
                recommendation_run_id=run.id,
                explanation=None,
            ))

        self.db.add(run)
        self.db.commit()
