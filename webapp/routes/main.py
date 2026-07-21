"""Main Routes — landing page and home dashboard."""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user
from sqlalchemy import func, text

from app.database import SessionLocal
from app.models.job import Job
from app.models.recommendation import SavedJob

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return render_template("landing.html")

    db = SessionLocal()
    try:
        total_jobs = db.query(Job).count()
        categories = (
            db.query(Job.category, func.count(Job.id))
            .group_by(Job.category)
            .order_by(func.count(Job.id).desc())
            .limit(5)
            .all()
        )

        saved_ids = {
            str(s.job_id) for s in
            db.query(SavedJob).filter(SavedJob.user_id == current_user.id).all()
        }

        # Build feed: jobs similar to saved jobs, else recent jobs
        feed_jobs = []
        feed_source = "saved"

        if saved_ids:
            # Find jobs similar to saved ones via embedding
            saved_job_ids = list(saved_ids)
            stmt = text("""
                SELECT DISTINCT j.id, j.title, j.title_clean, j.company,
                       j.location_city, j.location_country, j.remote,
                       j.salary_min, j.salary_max, j.salary_currency,
                       j.category, j.job_type, j.url, j.source, j.created_at,
                       MAX(1 - (j.embedding <=> ref.embedding)) AS similarity
                FROM jobs j
                CROSS JOIN jobs ref
                WHERE ref.id = ANY(:saved_ids)
                  AND j.id != ref.id
                  AND j.embedding IS NOT NULL
                  AND ref.embedding IS NOT NULL
                  AND j.id != ALL(:saved_ids)
                GROUP BY j.id, j.title, j.title_clean, j.company,
                         j.location_city, j.location_country, j.remote,
                         j.salary_min, j.salary_max, j.salary_currency,
                         j.category, j.job_type, j.url, j.source, j.created_at
                ORDER BY similarity DESC
                LIMIT 20
            """)
            rows = db.execute(stmt, {"saved_ids": saved_job_ids}).fetchall()
            feed_jobs = rows

        if not feed_jobs:
            feed_jobs = db.query(Job).order_by(Job.created_at.desc()).limit(10).all()
            feed_source = "recent"

        return render_template(
            "main/home.html",
            total_jobs=total_jobs,
            categories=categories,
            feed_jobs=feed_jobs,
            feed_source=feed_source,
            saved_ids=saved_ids,
        )
    finally:
        db.close()
