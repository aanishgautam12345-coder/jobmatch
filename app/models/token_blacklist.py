"""Token Revocation — blacklist JWT tokens on logout or password reset.

Adds a `token_blacklist` table and utility functions to:
- Blacklist a token (on logout, password reset, account deactivation)
- Check if a token is blacklisted (during auth validation)
- Clean up expired blacklisted tokens periodically
"""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TokenBlacklist(Base):
    """A blacklisted JWT token that should no longer be accepted."""

    __tablename__ = "token_blacklist"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token_jti: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )  # JWT "jti" claim (unique token ID)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(String(50), default="logout")
    # Reasons: logout, password_reset, account_deactivated, security
    blacklisted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

def blacklist_token(db, token_jti: str, user_id: uuid.UUID, reason: str = "logout", expires_at: datetime | None = None):
    """Stage a token blacklist entry in the caller's transaction."""
    from datetime import timedelta
    entry = TokenBlacklist(
        id=uuid.uuid4(),
        token_jti=token_jti,
        user_id=user_id,
        reason=reason,
        expires_at=expires_at or (datetime.utcnow() + timedelta(hours=24)),
    )
    db.add(entry)


def is_token_blacklisted(db, token_jti: str) -> bool:
    """Check if a token has been blacklisted."""
    return db.query(TokenBlacklist).filter(TokenBlacklist.token_jti == token_jti).first() is not None


def cleanup_expired_blacklist(db):
    """Remove blacklisted tokens that have already expired."""
    from sqlalchemy import delete
    db.execute(delete(TokenBlacklist).where(TokenBlacklist.expires_at < datetime.utcnow()))
    db.commit()
