"""Recommendations API — get personalised job recommendations.

Endpoints:
    GET  /me/recommendations          — get ranked recommendations for current user
    GET  /me/recommendations/{job_id} — get single recommendation detail
    POST /explain/{job_id}            — generate RAG explanation for a job match
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserProfile
from app.models.job import Job, JobSkill
from app.models.recommendation import Recommendation
from app.core.deps import get_current_user
from app.agents.recommendation_agent import RecommendationAgent
from app.services.rag import generate_explanation
from app.services.recommendation import compute_match_score, MatchBreakdown
from app.services.profile_completeness import calculate_completeness

router = APIRouter()


class RecommendationResponse(BaseModel):
    job_id: str
    title: str
    company: str | None
    location_city: str | None
    location_country: str | None
    remote: bool
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    category: str | None
    job_type: str | None
    url: str | None
    rank: int
    match_percentage: float
    breakdown: dict
    matching_skills: list[str]
    missing_skills: list[str]
    explanation: str | None = None


class RecommendationsListResponse(BaseModel):
    count: int
    profile_headline: str | None
    profile_completeness: float | None = None
    completeness_recommendations: list[str] | None = None
    results: list[RecommendationResponse]


class ExplainRequest(BaseModel):
    job_id: str


class ExplainResponse(BaseModel):
    explanation: str
    match_percentage: float


@router.get("/me/recommendations", response_model=RecommendationsListResponse)
def get_recommendations(
    top_n: int = 10,
    hard_filter_remote: bool = False,
    hard_filter_locations: str | None = None,  # comma-separated
    hard_filter_min_salary: float | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get ranked job recommendations for the current user.

    Runs the full recommendation pipeline with optional hard constraints.
    Hard constraints completely exclude non-matching jobs before scoring.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Create a profile first.")

    # Calculate profile completeness
    completeness = calculate_completeness(profile)

    # Check minimum profile data
    if not profile.skills and not profile.headline:
        raise HTTPException(
            status_code=400,
            detail="Profile must have at least skills or headline for recommendations.",
        )

    # Build hard constraints from query params
    hard_constraints = None
    if hard_filter_remote or hard_filter_locations or hard_filter_min_salary:
        hard_constraints = {}
        if hard_filter_remote:
            hard_constraints["remote_only"] = True
        if hard_filter_locations:
            hard_constraints["locations"] = [loc.strip() for loc in hard_filter_locations.split(",")]
        if hard_filter_min_salary:
            hard_constraints["min_salary"] = hard_filter_min_salary

    # Run recommendation agent
    agent = RecommendationAgent(db)
    recommendations = agent.recommend(profile, top_n=top_n, hard_constraints=hard_constraints)

    # Fetch explanations
    rec_ids = [r["job_id"] for r in recommendations]
    explanations = {}
    if rec_ids:
        rec_records = (
            db.query(Recommendation)
            .filter(
                Recommendation.user_id == user.id,
                Recommendation.job_id.in_(rec_ids),
            )
            .all()
        )
        for rec in rec_records:
            if rec.explanation:
                explanations[str(rec.job_id)] = rec.explanation

    for rec in recommendations:
        rec["explanation"] = explanations.get(rec["job_id"])

    return RecommendationsListResponse(
        count=len(recommendations),
        profile_headline=profile.headline,
        profile_completeness=completeness.overall,
        completeness_recommendations=completeness.recommendations if completeness.overall < 70 else None,
        results=[RecommendationResponse(**r) for r in recommendations],
    )


@router.get("/me/recommendations/{job_id}", response_model=RecommendationResponse)
def get_recommendation_detail(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific recommendation with full breakdown."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    job = db.query(Job).filter(Job.id == job_id, Job.is_active.is_(True)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_skills = [s.skill for s in db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]

    # Get similarity from DB
    from sqlalchemy import select
    stmt = select((1 - Job.embedding.cosine_distance(profile.profile_embedding)).label("similarity")).where(Job.id == job.id)
    result = db.execute(stmt).first()
    similarity_value = float(result[0]) if result else 0.5

    breakdown = compute_match_score(
        profile, job, job_skills, similarity_value,
        profile.preferred_job_types
    )

    rec = db.query(Recommendation).filter(
        Recommendation.user_id == user.id,
        Recommendation.job_id == job.id,
    ).first()

    return RecommendationResponse(
        job_id=str(job.id),
        title=job.title_clean or job.title,
        company=job.company,
        location_city=job.location_city,
        location_country=job.location_country,
        remote=job.remote,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        category=job.category,
        job_type=job.job_type,
        url=job.url,
        rank=rec.rank if rec else 0,
        match_percentage=breakdown.match_percentage,
        breakdown={
            "semantic_similarity": round(breakdown.semantic_similarity * 100, 1),
            "skill_overlap": round(breakdown.skill_overlap * 100, 1),
            "location_fit": round(breakdown.location_fit * 100, 1),
            "salary_fit": round(breakdown.salary_fit * 100, 1),
            "experience_fit": round(breakdown.experience_fit * 100, 1),
            "job_type_fit": round(breakdown.job_type_fit * 100, 1),
        },
        matching_skills=breakdown.matching_skills,
        missing_skills=breakdown.missing_skills,
        explanation=rec.explanation if rec else None,
    )


@router.post("/explain/{job_id}", response_model=ExplainResponse)
def explain_recommendation(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a RAG explanation for why a job matches the user's profile."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    job = db.query(Job).filter(Job.id == job_id, Job.is_active.is_(True)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_skills = [s.skill for s in db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]

    from sqlalchemy import select
    stmt = select((1 - Job.embedding.cosine_distance(profile.profile_embedding)).label("similarity")).where(Job.id == job.id)
    result = db.execute(stmt).first()
    similarity_value = float(result[0]) if result else 0.5

    breakdown = compute_match_score(
        profile, job, job_skills, similarity_value,
        profile.preferred_job_types
    )

    explanation = generate_explanation(profile, job, breakdown)

    rec = db.query(Recommendation).filter(
        Recommendation.user_id == user.id,
        Recommendation.job_id == job.id,
    ).first()
    if rec:
        rec.explanation = explanation
        db.commit()

    return ExplainResponse(
        explanation=explanation,
        match_percentage=breakdown.match_percentage,
    )
