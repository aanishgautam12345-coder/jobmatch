"""Job Posting — a specific source posting that contributes to a canonical job.

One canonical job may have multiple source postings from different platforms
(e.g., the same role posted on Adzuna and Reed). Each posting preserves the
original data from its source for traceability and re-processing.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class JobPosting(Base):
    """A specific source posting linked to a canonical job."""

    __tablename__ = "job_postings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    raw_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_jobs.id", ondelete="SET NULL")
    )

    # Source identification
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1000))

    # Original (unprocessed) data from the source
    original_title: Mapped[str | None] = mapped_column(String(500))
    original_description: Mapped[str | None] = mapped_column(Text)
    original_location: Mapped[str | None] = mapped_column(String(500))
    original_salary_text: Mapped[str | None] = mapped_column(String(255))
    original_currency: Mapped[str | None] = mapped_column(String(10))
    original_company: Mapped[str | None] = mapped_column(String(255))

    # Raw payload for re-processing
    payload: Mapped[dict | None] = mapped_column(JSONB)

    # Timestamps
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Relationships
    canonical_job: Mapped["Job"] = relationship(back_populates="postings")  # noqa: F821
    raw_job: Mapped["RawJob | None"] = relationship()  # noqa: F821

    __table_args__ = (
        Index("ix_posting_source_job", "source", "source_job_id", unique=True),
        Index("ix_posting_canonical", "canonical_job_id", "is_active"),
    )
