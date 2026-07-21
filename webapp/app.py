"""JobMatch AI - Flask Application Factory.

Run with:
    python run.py

This is the new frontend, replacing the Streamlit dashboard, with a
proper session-based login system and a real job-portal design.
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from app.database import SessionLocal, init_db
from app.models.user import User
from app.config import get_settings

logger = logging.getLogger(__name__)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"

# CSRF protection
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    settings = get_settings()
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB max upload
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600  # 1 hour

    # Ensure DB tables exist
    init_db()

    login_manager.init_app(app)
    csrf.init_app(app)

    app.jinja_env.filters["ord"] = ord

    def format_description(text):
        """Convert ALL CAPS descriptions to readable sentence case."""
        if not text:
            return ""
        import re as _re
        # If more than 70% of letters are uppercase, convert to sentence case
        letters = [c for c in text if c.isalpha()]
        if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7:
            # Split into sentences, capitalise first letter of each
            sentences = _re.split(r'(?<=[.!?])\s+', text.lower())
            text = ' '.join(s.strip().capitalize() for s in sentences if s.strip())
        # Collapse 3+ newlines to 2
        text = _re.sub(r'\n{3,}', '\n\n', text)
        return text

    app.jinja_env.filters["format_description"] = format_description

    @login_manager.user_loader
    def load_user(user_id):
        import uuid as uuid_lib
        from sqlalchemy.orm import joinedload
        db = SessionLocal()
        try:
            user = (
                db.query(User)
                .options(joinedload(User.profile))
                .filter(User.id == uuid_lib.UUID(user_id))
                .first()
            )
            if user:
                db.expunge(user)
            return user
        finally:
            db.close()

    @app.template_global()
    def company_logo_color(name):
        colors = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6','#1abc9c','#e67e22','#34495e','#16a085','#c0392b','#2980b9','#8e44ad']
        idx = sum(ord(c) for c in (name or '?')) % len(colors)
        return colors[idx]

    @app.template_global()
    def company_initials(name):
        if not name:
            return '?'
        words = name.split()
        if len(words) >= 2:
            return (words[0][0] + words[1][0]).upper()
        return name[:2].upper()

    @app.route("/health")
    def health():
        from flask import jsonify
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        finally:
            db.close()
        status = 200 if db_ok else 503
        return jsonify({
            "status": "healthy" if db_ok else "degraded",
            "service": "webapp",
            "database": "connected" if db_ok else "disconnected",
        }), status

    # Register blueprints
    from webapp.routes.auth import auth_bp
    from webapp.routes.main import main_bp
    from webapp.routes.jobs import jobs_bp
    from webapp.routes.profile import profile_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(profile_bp)

    logger.info("Flask app created with CSRF protection")
    return app
