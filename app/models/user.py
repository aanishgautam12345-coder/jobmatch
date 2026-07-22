import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.config import get_settings


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False)
    notification_pref: Mapped["NotificationPreference"] = relationship(
        back_populates="user", uselist=False
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="user")  # noqa: F821
    saved_jobs: Mapped[list["SavedJob"]] = relationship(back_populates="user")  # noqa: F821

    # ── Flask-Login interface ──
    # Implemented manually (not via UserMixin) since `is_active` is already
    # a real database column and UserMixin would shadow it as a property.
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255))
    headline: Mapped[str | None] = mapped_column(String(500))
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    experience_years: Mapped[int | None] = mapped_column(Integer)
    experience_level: Mapped[str | None] = mapped_column(String(50))  # junior/mid/senior
    preferred_locations: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    preferred_job_types: Mapped[list[str] | None] = mapped_column(ARRAY(String))  # full-time/part-time/contract
    min_salary: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(10), default="USD")
    career_interests: Mapped[str | None] = mapped_column(Text)

    # The user's profile as a vector — recomputed on every profile save
    profile_embedding = mapped_column(Vector(get_settings().embedding_dim), nullable=True)

    user: Mapped["User"] = relationship(back_populates="profile")


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_match_score: Mapped[float] = mapped_column(Float, default=0.70)  # only notify above 70%
    frequency: Mapped[str] = mapped_column(String(20), default="daily")  # instant/daily/weekly
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="notification_pref")
