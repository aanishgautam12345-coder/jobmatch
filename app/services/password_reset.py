"""Shared password-reset workflow for FastAPI and Flask."""

import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import create_access_token, decode_access_token, hash_password
from app.models.token_blacklist import blacklist_token, is_token_blacklisted
from app.models.user import User
from app.services.email import send_password_reset_email

logger = logging.getLogger(__name__)

GENERIC_RESET_MESSAGE = "If that email exists, a password reset link has been sent."


class InvalidResetTokenError(ValueError):
    pass


class InvalidPasswordError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise InvalidPasswordError("Password must be at least 8 characters.")


def request_password_reset(db: Session, email: str) -> None:
    """Send a reset link for an active account without exposing its existence."""
    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email, User.is_active.is_(True)).first()
    if not user:
        return

    settings = get_settings()
    token = create_access_token(
        {"sub": str(user.id), "purpose": "password_reset"},
        expires_minutes=settings.password_reset_expiry_minutes,
    )
    reset_url = f"{settings.app_base_url.rstrip('/')}/auth/reset-password/{token}"
    delivered = send_password_reset_email(user.email, reset_url)
    if delivered:
        logger.info("Password reset email delivered for user_id=%s", user.id)
    else:
        logger.warning("Password reset email delivery failed for user_id=%s", user.id)


def reset_password(db: Session, token: str, new_password: str) -> User:
    """Consume a reset token and update the password in one transaction."""
    validate_password(new_password)
    payload = decode_access_token(token)
    if not payload or payload.get("purpose") != "password_reset":
        raise InvalidResetTokenError("Invalid or expired reset token")

    jti = payload.get("jti")
    subject = payload.get("sub")
    expires_at = payload.get("exp")
    if not all((jti, subject, expires_at)) or is_token_blacklisted(db, jti):
        raise InvalidResetTokenError("Invalid or expired reset token")

    try:
        user_id = uuid.UUID(subject)
    except (TypeError, ValueError) as exc:
        raise InvalidResetTokenError("Invalid or expired reset token") from exc

    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise InvalidResetTokenError("Invalid or expired reset token")

    user.password_hash = hash_password(new_password)
    blacklist_token(
        db,
        jti,
        user.id,
        reason="password_reset",
        expires_at=datetime.utcfromtimestamp(expires_at),
    )
    db.commit()
    return user
