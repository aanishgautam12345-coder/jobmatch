"""Profile Routes — view/edit profile, with integrated resume upload."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app.database import SessionLocal
from app.models.user import UserProfile
from app.services.embedding import build_profile_text, generate_embedding
from app.services.resume_parser import process_resume
from app.services.explanation_validator import (
    InvalidResumeError,
    ResumeConfigurationError,
    ResumeProviderError,
    ResumeResponseError,
)

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")

ALLOWED_EXTENSIONS = {"pdf"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@profile_bp.route("/", methods=["GET", "POST"])
@login_required
def view_profile():
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

        if request.method == "POST":
            skills_text = request.form.get("skills", "")
            locations_text = request.form.get("preferred_locations", "")

            profile.full_name = request.form.get("full_name", "").strip() or None
            profile.headline = request.form.get("headline", "").strip() or None
            profile.skills = [s.strip().lower() for s in skills_text.split(",") if s.strip()]
            profile.preferred_locations = [l.strip() for l in locations_text.split(",") if l.strip()]
            profile.experience_level = request.form.get("experience_level") or None
            exp_years = request.form.get("experience_years")
            profile.experience_years = int(exp_years) if exp_years else None
            min_salary = request.form.get("min_salary")
            profile.min_salary = float(min_salary) if min_salary else None
            profile.salary_currency = request.form.get("salary_currency") or "USD"
            profile.career_interests = request.form.get("career_interests", "").strip() or None

            text = build_profile_text(
                headline=profile.headline, skills=profile.skills,
                career_interests=profile.career_interests,
                experience_level=profile.experience_level,
            )
            profile.profile_embedding = generate_embedding(text)

            db.commit()
            flash("Profile saved successfully.", "success")
            return redirect(url_for("profile.view_profile"))

        return render_template("main/profile.html", profile=profile)
    finally:
        db.close()


@profile_bp.route("/upload-resume", methods=["POST"])
@login_required
def upload_resume():
    """AJAX endpoint — parses an uploaded PDF resume and returns extracted fields.

    The frontend then pre-fills the profile form with this data; the user
    reviews and confirms via the normal Save button.
    """
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not _allowed_file(file.filename):
        return jsonify({"error": "Only PDF files are supported"}), 400

    try:
        pdf_bytes = file.read()
        extracted = process_resume(pdf_bytes)
        return jsonify({"success": True, "data": extracted})
    except InvalidResumeError:
        return jsonify({"error": "Could not parse the uploaded PDF. Make sure it's a text-based resume, not a scanned image."}), 400
    except (ResumeConfigurationError, ResumeProviderError, ResumeResponseError):
        return jsonify({"error": "Resume processing is temporarily unavailable. Please try again later."}), 503
    except Exception:
        return jsonify({"error": "An unexpected error occurred. Please try again later."}), 500
