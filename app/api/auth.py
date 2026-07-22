"""Auth API — Registration, Login, Logout, and Password Recovery.

Endpoints:
    POST /api/auth/register  — create a new user account
    POST /api/auth/login     — authenticate and receive JWT token
    POST /api/auth/logout     — revoke the current token
    POST /api/auth/forgot    — request a password reset token
    POST /api/auth/reset     — reset password using the token

Rate limited: 5 attempts/minute on login/register, 3/minute on forgot/reset.
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserProfile, NotificationPreference
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.core.deps import get_current_user
from app.models.token_blacklist import blacklist_token
from app.services.password_reset import (
    GENERIC_RESET_MESSAGE,
    InvalidPasswordError,
    InvalidResetTokenError,
    request_password_reset,
    reset_password as consume_password_reset,
    validate_password,
)

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
oauth2_scheme_from_header = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Request/Response schemas ──

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MessageResponse(BaseModel):
    message: str


# ── Endpoints ──

@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, req: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account with profile and notification preferences."""
    email = req.email.strip().lower()
    try:
        validate_password(req.password)
    except InvalidPasswordError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    db.flush()

    profile = UserProfile(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name=req.full_name,
    )
    db.add(profile)

    prefs = NotificationPreference(
        id=uuid.uuid4(),
        user_id=user.id,
        email_enabled=True,
        min_match_score=0.5,
        frequency="daily",
    )
    db.add(prefs)
    db.commit()

    token = create_access_token(data={"sub": str(user.id)})
    logger.info("User registered: user_id=%s", user.id)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT token."""
    user = db.query(User).filter(User.email == req.email.strip().lower()).first()

    if not user or not verify_password(req.password, user.password_hash):
        logger.warning("Failed login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    token = create_access_token(data={"sub": str(user.id)})
    logger.info("User logged in: user_id=%s", user.id)
    return TokenResponse(access_token=token)


@router.post("/logout", response_model=MessageResponse)
def logout(
    user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme_from_header),
    db: Session = Depends(get_db),
):
    """Revoke the current JWT token (logout)."""
    payload = decode_access_token(token)
    if payload:
        jti = payload.get("jti")
        if jti:
            blacklist_token(
                db, jti, user.id, reason="logout",
                expires_at=datetime.utcfromtimestamp(payload.get("exp", 0)),
            )
            db.commit()
    logger.info("User logged out: user_id=%s", user.id)
    return MessageResponse(message="Successfully logged out")


@router.post("/forgot", response_model=MessageResponse)
@limiter.limit("3/minute")
def forgot_password(request: Request, req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Request a password reset. Always returns success to avoid email enumeration."""
    request_password_reset(db, req.email)
    return MessageResponse(message=GENERIC_RESET_MESSAGE)


@router.post("/reset", response_model=MessageResponse)
@limiter.limit("3/minute")
def reset_password(request: Request, req: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset password using a token from /forgot."""
    try:
        user = consume_password_reset(db, req.token, req.new_password)
    except (InvalidResetTokenError, InvalidPasswordError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Password reset completed for user_id=%s", user.id)
    return MessageResponse(message="Password has been reset successfully.")
