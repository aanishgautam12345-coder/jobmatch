"""Processing Error — logs failures during the ingestion/processing pipeline.

When a raw job record fails processing, the error is logged here instead of
silently marking the record as processed. This enables:
- Debugging processing failures
- Data quality monitoring
- Retry logic for transient errors
"""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class ProcessingError(Base):
    """A single processing failure for a raw job record."""

    __tablename__ = "processing_errors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL"), index=True
    )
    raw_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_jobs.id", ondelete="SET NULL"), index=True
    )

    # Error classification
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Types: salary_parse_error, location_parse_error, embedding_error,
    #        skill_extraction_error, dedup_error, validation_error, unknown_error

    # Error details
    error_message: Mapped[str | None] = mapped_column(Text)
    stack_trace: Mapped[str | None] = mapped_column(Text)

    # Source context
    source: Mapped[str | None] = mapped_column(String(50))
    source_job_id: Mapped[str | None] = mapped_column(String(255))

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(default=0)
    resolved: Mapped[bool] = mapped_column(default=False)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
