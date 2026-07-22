"""Extended Jobs API â€” Saved Jobs, Skill Search, Company Search, Recently Added.

Adds the missing features from the requirements audit.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.job import Job, JobSkill
from app.models.recommendation import SavedJob
from app.models.user import User
from app.core.deps import get_current_user

router = APIRouter()


# â”€â”€ Saved Jobs â”€â”€

@router.post("/saved/{job_id}", status_code=201)
def save_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a job to the user's saved list."""
    job = db.query(Job).filter(Job.id == job_id, Job.is_active.is_(True)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    existing = db.query(SavedJob).filter(
        SavedJob.user_id == user.id, SavedJob.job_id == job_id
    ).first()
    if existing:
        return {"message": "Job already saved"}

    db.add(SavedJob(id=uuid.uuid4(), user_id=user.id, job_id=uuid.UUID(job_id)))
    db.commit()
    return {"message": "Job saved"}


@router.delete("/saved/{job_id}")
def unsave_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a job from the user's saved list."""
    saved = db.query(SavedJob).filter(
        SavedJob.user_id == user.id, SavedJob.job_id == job_id
    ).first()
    if not saved:
        raise HTTPException(status_code=404, detail="Saved job not found")

    db.delete(saved)
    db.commit()
    return {"message": "Job removed from saved list"}


@router.get("/saved")
def get_saved_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all saved jobs for the current user."""
    saved = (
        db.query(SavedJob, Job)
        .join(Job, Job.id == SavedJob.job_id)
        .filter(SavedJob.user_id == user.id, Job.is_active.is_(True))
        .order_by(SavedJob.saved_at.desc())
        .all()
    )
    return {
        "count": len(saved),
        "results": [
            {
                "job_id": str(s.id),
                "saved_at": str(s.saved_at),
                "title": j.title_clean or j.title,
                "company": j.company,
                "location_city": j.location_city,
                "location_country": j.location_country,
                "remote": j.remote,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "salary_currency": j.salary_currency,
                "category": j.category,
                "url": j.url,
            }
            for s, j in saved
        ],
    }


# â”€â”€ Skill Search â”€â”€

@router.get("/search/skills")
def search_by_skills(
    skills: str = Query(..., description="Comma-separated skill list, e.g. 'python,django,aws'"),
    match_all: bool = Query(False, description="If true, job must have ALL skills; if false, any"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Search jobs by required skills â€” matches against the job_skills table."""
    skill_list = [s.strip().lower() for s in skills.split(",") if s.strip()]
    if not skill_list:
        raise HTTPException(status_code=400, detail="Provide at least one skill")

    if match_all:
        # Jobs that have ALL specified skills
        stmt = (
            select(Job.id)
            .join(JobSkill, JobSkill.job_id == Job.id)
            .where(Job.is_active.is_(True), func.lower(JobSkill.skill).in_(skill_list))
            .group_by(Job.id)
            .having(func.count(func.distinct(JobSkill.skill)) >= len(skill_list))
        )
    else:
        # Jobs that have ANY of the specified skills
        stmt = (
            select(Job.id)
            .join(JobSkill, JobSkill.job_id == Job.id)
            .where(Job.is_active.is_(True), func.lower(JobSkill.skill).in_(skill_list))
            .group_by(Job.id)
        )

    matching_ids = [row[0] for row in db.execute(stmt).all()]

    if not matching_ids:
        return {"query_skills": skill_list, "count": 0, "results": []}

    jobs = (
        db.query(Job)
        .filter(Job.id.in_(matching_ids), Job.is_active.is_(True))
        .limit(limit)
        .all()
    )

    return {
        "query_skills": skill_list,
        "match_mode": "all" if match_all else "any",
        "count": len(jobs),
        "results": [
            {
                "id": str(j.id),
                "title": j.title_clean or j.title,
                "company": j.company,
                "location_city": j.location_city,
                "location_country": j.location_country,
                "remote": j.remote,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "category": j.category,
                "skills": [s.skill for s in j.skills],
                "url": j.url,
            }
            for j in jobs
        ],
    }


# â”€â”€ Company Search â”€â”€

@router.get("/search/company")
def search_by_company(
    q: str = Query(..., description="Company name to search for"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Search jobs by company name (partial match)."""
    pattern = f"%{q}%"
    jobs = (
        db.query(Job)
        .filter(Job.company.ilike(pattern), Job.is_active.is_(True))
        .order_by(Job.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "query": q,
        "count": len(jobs),
        "results": [
            {
                "id": str(j.id),
                "title": j.title_clean or j.title,
                "company": j.company,
                "location_city": j.location_city,
                "location_country": j.location_country,
                "remote": j.remote,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "category": j.category,
                "url": j.url,
            }
            for j in jobs
        ],
    }


# â”€â”€ Recently Added Jobs â”€â”€

@router.get("/recent")
def get_recent_jobs(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Get the most recently added jobs."""
    jobs = (
        db.query(Job)
        .filter(Job.is_active.is_(True))
        .order_by(Job.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "count": len(jobs),
        "results": [
            {
                "id": str(j.id),
                "title": j.title_clean or j.title,
                "company": j.company,
                "location_city": j.location_city,
                "location_country": j.location_country,
                "remote": j.remote,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "salary_currency": j.salary_currency,
                "category": j.category,
                "url": j.url,
                "source": j.source,
                "created_at": str(j.created_at),
            }
            for j in jobs
        ],
    }


# â”€â”€ Similar Skill Matching â”€â”€

@router.get("/search/similar-skills")
def search_similar_skills(
    skills: str = Query(..., description="Comma-separated skills to embed and search, e.g. 'python,django'"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Semantic skill matching â€” embeds the skill set and finds jobs with
    similar skill requirements using vector similarity.

    Unlike /search/skills (exact dictionary match), this uses the embedding
    model to find jobs that require CONCEPTUALLY similar skills, even if
    the exact words don't match (e.g. 'react' finds 'frontend framework' jobs).
    """
    from app.services.embedding import generate_embedding

    skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    if not skill_list:
        raise HTTPException(status_code=400, detail="Provide at least one skill")

    query_text = "Skills: " + ", ".join(skill_list)
    query_embedding = generate_embedding(query_text, is_query=True)

    distance = Job.embedding.cosine_distance(query_embedding)

    stmt = (
        select(
            Job.id, Job.title, Job.title_clean, Job.company,
            Job.location_city, Job.location_country, Job.remote,
            Job.salary_min, Job.salary_max, Job.salary_currency,
            Job.category, Job.url,
            (1 - distance).label("similarity"),
        )
        .where(Job.embedding.isnot(None), Job.is_active.is_(True))
        .order_by(distance)
        .limit(limit)
    )

    results = db.execute(stmt).all()

    return {
        "query_skills": skill_list,
        "count": len(results),
        "results": [
            {
                "id": str(row.id),
                "title": row.title_clean or row.title,
                "company": row.company,
                "location_city": row.location_city,
                "location_country": row.location_country,
                "remote": row.remote,
                "salary_min": row.salary_min,
                "salary_max": row.salary_max,
                "salary_currency": row.salary_currency,
                "category": row.category,
                "url": row.url,
                "similarity": round(float(row.similarity), 4),
                "match_percentage": round(float(row.similarity) * 100, 1),
            }
            for row in results
        ],
    }
