"""Recommendation Run — audit trail for recommendation generation.

Every call to the recommendation agent creates a RecommendationRun record
that captures the exact configuration, retrieval method, candidate pool size,
scoring parameters, and latency. This makes every recommendation set
reproducible and auditable.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class RecommendationRun(Base):
    """Audit trail for a single recommendation generation run."""

    __tablename__ = "recommendation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Retrieval configuration
    retrieval_method: Mapped[str] = mapped_column(String(50), nullable=False)  # semantic/hybrid/lexical
    candidate_pool_size: Mapped[int] = mapped_column(Integer, default=0)
    final_pool_size: Mapped[int] = mapped_column(Integer, default=0)

    # Model versions
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    reranker_model: Mapped[str | None] = mapped_column(String(100))

    # Scoring configuration (JSON snapshot of weights and thresholds)
    scoring_config: Mapped[dict | None] = mapped_column(JSONB)

    # Performance
    latency_ms: Mapped[float | None] = mapped_column(Float)

    # Agent decisions
    agent_decisions: Mapped[dict | None] = mapped_column(JSONB)  # e.g. {"expanded_pool": true, "reason": "low quality"}

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="running")  # running/completed/failed
    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationships
    recommendations: Mapped[list["Recommendation"]] = relationship(  # noqa: F821
        back_populates="recommendation_run"
    )
