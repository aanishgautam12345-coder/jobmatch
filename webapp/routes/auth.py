"""Auth Routes — session-based login/register/logout using Flask-Login."""

import uuid

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.database import SessionLocal
from app.models.user import User, UserProfile, NotificationPreference
from app.core.security import hash_password, verify_password
from app.services.password_reset import (
    GENERIC_RESET_MESSAGE,
    InvalidPasswordError,
    InvalidResetTokenError,
    request_password_reset,
    reset_password as consume_password_reset,
    validate_password,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        full_name = request.form.get("full_name", "").strip()

        # Validation
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("auth/register.html")

        try:
            validate_password(password)
        except InvalidPasswordError as exc:
            flash(str(exc), "error")
            return render_template("auth/register.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("auth/register.html")

        db = SessionLocal()
        try:
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                flash("An account with this email already exists.", "error")
                return render_template("auth/register.html")

            user = User(id=uuid.uuid4(), email=email, password_hash=hash_password(password))
            db.add(user)
            db.flush()

            profile = UserProfile(id=uuid.uuid4(), user_id=user.id, full_name=full_name or None)
            db.add(profile)

            prefs = NotificationPreference(
                id=uuid.uuid4(), user_id=user.id,
                email_enabled=True, min_match_score=0.5, frequency="daily",
            )
            db.add(prefs)

            db.commit()
            db.refresh(user)

            login_user(user)
            flash("Welcome to JobMatch AI! Let's build your profile.", "success")
            return redirect(url_for("profile.view_profile"))

        finally:
            db.close()

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()

            if not user or not verify_password(password, user.password_hash):
                flash("Incorrect email or password.", "error")
                return render_template("auth/login.html")

            if not user.is_active:
                flash("This account has been deactivated.", "error")
                return render_template("auth/login.html")

            login_user(user, remember=remember)
            flash(f"Welcome back!", "success")

            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.index"))

        finally:
            db.close()

    return render_template("auth/login.html")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        db = SessionLocal()
        try:
            request_password_reset(db, request.form.get("email", ""))
        finally:
            db.close()
        flash(GENERIC_RESET_MESSAGE, "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")
        if password != confirmation:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html", token=token)
        db = SessionLocal()
        try:
            consume_password_reset(db, token, password)
        except (InvalidResetTokenError, InvalidPasswordError) as exc:
            db.rollback()
            flash(str(exc), "error")
            return render_template("auth/reset_password.html", token=token)
        finally:
            db.close()
        flash("Password has been reset. You can now sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", token=token)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("main.index"))
