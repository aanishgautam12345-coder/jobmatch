"""Jobs Routes — search, recommendations, saved jobs, recent jobs."""

import uuid

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.database import SessionLocal
from app.models.job import Job, JobSkill
from app.models.recommendation import SavedJob
from app.services.search import evidence_search, semantic_search, keyword_search, hybrid_search, format_salary_display
from app.agents.recommendation_agent import RecommendationAgent
from app.services.recommendation import compute_match_score
from app.services.rag import generate_explanation
from app.processing.category import CATEGORIES

jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs")


@jobs_bp.route("/search")
@login_required
def search():
    query = request.args.get("q", "").strip()
    country = request.args.get("country", "").strip()
    category = request.args.get("category", "")
    remote_only = request.args.get("remote_only") == "on"

    results = []
    if query:
        db = SessionLocal()
        try:
            if country or category or remote_only:
                results = hybrid_search(
                    db, query=query, location_country=country or None,
                    remote_only=remote_only, category=category or None, limit=20,
                )
            else:
                results = evidence_search(db, query=query, limit=20)

            saved_ids = {
                str(s.job_id) for s in
                db.query(SavedJob).filter(SavedJob.user_id == current_user.id).all()
            }
            for r in results:
                r["is_saved"] = r["id"] in saved_ids
                r["salary_display"] = format_salary_display(
                    r.get("salary_min"), r.get("salary_max"),
                    r.get("salary_currency"), r.get("salary_period"),
                )
        finally:
            db.close()

    return render_template(
        "main/search.html", query=query, results=results,
        categories=CATEGORIES, selected_category=category,
        country=country, remote_only=remote_only,
    )


@jobs_bp.route("/recommendations")
@login_required
def recommendations():
    db = SessionLocal()
    try:
        profile = current_user.profile

        if not profile or (not profile.skills and not profile.headline):
            return render_template("main/recommendations.html", recs=None, no_profile=True)

        agent = RecommendationAgent(db)
        recs = agent.recommend(profile, top_n=10)

        saved_ids = {
            str(s.job_id) for s in
            db.query(SavedJob).filter(SavedJob.user_id == current_user.id).all()
        }
        for r in recs:
            r["is_saved"] = r["job_id"] in saved_ids

        return render_template("main/recommendations.html", recs=recs, no_profile=False)
    finally:
        db.close()


@jobs_bp.route("/<job_id>")
@login_required
def job_detail(job_id):
    """Full job detail page with description, skills, match breakdown, and similar jobs."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return "Job not found", 404

        skills = [s.skill for s in db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]

        saved_ids = {
            str(s.job_id) for s in
            db.query(SavedJob).filter(SavedJob.user_id == current_user.id).all()
        }
        is_saved = str(job.id) in saved_ids

        similar_jobs = []
        if job.embedding is not None:
            from sqlalchemy import text
            stmt = text("""
                SELECT id, title, title_clean, company, location_city, location_country, remote, category,
                       (1 - (embedding <=> :embedding)) AS similarity
                FROM jobs
                WHERE id != :job_id AND embedding IS NOT NULL
                ORDER BY embedding <=> :embedding
                LIMIT 5
            """)
            rows = db.execute(stmt, {"embedding": str(job.embedding), "job_id": job.id}).fetchall()
            similar_jobs = rows

        breakdown = None
        matching_skills = []
        missing_skills = []
        profile = current_user.profile
        if profile and (profile.skills or profile.headline):
            import numpy as np
            if profile.profile_embedding is not None and job.embedding is not None:
                a, b = np.array(profile.profile_embedding), np.array(job.embedding)
                denom = np.linalg.norm(a) * np.linalg.norm(b)
                similarity = float(np.dot(a, b) / denom) if denom else 0.0
            else:
                similarity = 0.0
            breakdown = compute_match_score(profile, job, skills, similarity, getattr(profile, 'preferred_job_types', None))
            matching_skills = breakdown.matching_skills
            missing_skills = breakdown.missing_skills

        return render_template(
            "main/job_detail.html",
            job=job, skills=skills, is_saved=is_saved,
            similar_jobs=similar_jobs, breakdown=breakdown,
            matching_skills=matching_skills, missing_skills=missing_skills,
        )
    finally:
        db.close()


@jobs_bp.route("/explain/<job_id>")
@login_required
def explain(job_id):
    """AJAX endpoint — generates a RAG explanation for a single job on demand."""
    db = SessionLocal()
    try:
        profile = current_user.profile
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job or not profile:
            return jsonify({"error": "Not found"}), 404

        job_skills = [s.skill for s in db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]

        import numpy as np
        if profile.profile_embedding is not None and job.embedding is not None:
            a, b = np.array(profile.profile_embedding), np.array(job.embedding)
            denom = np.linalg.norm(a) * np.linalg.norm(b)
            similarity = float(np.dot(a, b) / denom) if denom else 0.0
        else:
            similarity = 0.0

        breakdown = compute_match_score(profile, job, job_skills, similarity, getattr(profile, 'preferred_job_types', None))
        explanation = generate_explanation(profile, job, breakdown)

        return jsonify({"explanation": explanation})
    finally:
        db.close()


@jobs_bp.route("/save/<job_id>", methods=["POST"])
@login_required
def save(job_id):
    db = SessionLocal()
    try:
        existing = db.query(SavedJob).filter(
            SavedJob.user_id == current_user.id, SavedJob.job_id == job_id
        ).first()
        if existing:
            return jsonify({"saved": True})

        db.add(SavedJob(id=uuid.uuid4(), user_id=current_user.id, job_id=uuid.UUID(job_id)))
        db.commit()
        return jsonify({"saved": True})
    finally:
        db.close()


@jobs_bp.route("/unsave/<job_id>", methods=["POST"])
@login_required
def unsave(job_id):
    db = SessionLocal()
    try:
        existing = db.query(SavedJob).filter(
            SavedJob.user_id == current_user.id, SavedJob.job_id == job_id
        ).first()
        if existing:
            db.delete(existing)
            db.commit()
        return jsonify({"saved": False})
    finally:
        db.close()


@jobs_bp.route("/saved")
@login_required
def saved():
    db = SessionLocal()
    try:
        rows = (
            db.query(SavedJob, Job)
            .join(Job, Job.id == SavedJob.job_id)
            .filter(SavedJob.user_id == current_user.id)
            .order_by(SavedJob.saved_at.desc())
            .all()
        )
        return render_template("main/saved.html", rows=rows)
    finally:
        db.close()


@jobs_bp.route("/recent")
@login_required
def recent():
    db = SessionLocal()
    try:
        jobs = db.query(Job).order_by(Job.created_at.desc()).limit(30).all()
        saved_ids = {
            str(s.job_id) for s in
            db.query(SavedJob).filter(SavedJob.user_id == current_user.id).all()
        }
        return render_template("main/recent.html", jobs=jobs, saved_ids=saved_ids)
    finally:
        db.close()
