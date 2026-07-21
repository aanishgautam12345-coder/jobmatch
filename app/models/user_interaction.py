"""User Interaction — tracks user actions on job listings.

Captures implicit and explicit feedback signals for future model improvement:
impressions, views, saves, dismissals, applications, and relevance judgments.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class UserInteraction(Base):
    """A single user interaction event with a job listing."""

    __tablename__ = "user_interactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )

    # Interaction type
    interaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    # Types: impression, view, save, unsave, dismiss, apply_clicked,
    #        marked_relevant, marked_irrelevant, notification_opened

    # Optional context (e.g., search query that led to impression, position in list)
    interaction_metadata: Mapped[dict | None] = mapped_column(JSONB, name="metadata")

    # Source context
    source: Mapped[str | None] = mapped_column(String(50))  # search/recommendation/notification
    recommendation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendation_runs.id", ondelete="SET NULL")
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        # Prevent duplicate interactions of the same type within a short window
        # (handled at application level, not DB constraint, for flexibility)
    )
