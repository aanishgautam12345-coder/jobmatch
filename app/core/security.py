"""Security utilities — password hashing and JWT token creation/verification."""

import logging
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from app.config import get_settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _truncate(password: str) -> str:
    """Bcrypt silently ignores bytes beyond 72. Truncate explicitly to avoid errors."""
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    return pwd_context.hash(_truncate(password))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_truncate(plain), hashed)


def create_access_token(data: dict, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    to_encode = {**data, "exp": expire, "iat": datetime.utcnow()}
    # Add jti (JWT ID) for token revocation support
    import uuid
    to_encode["jti"] = str(uuid.uuid4())
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


def get_token_jti(token: str) -> str | None:
    """Extract the jti claim from a token without verifying signature.
    Used for blacklist checks."""
    try:
        from jose import jwt as jose_jwt
        unverified = jose_jwt.get_unverified_claims(token)
        return unverified.get("jti")
    except Exception:
        return None
