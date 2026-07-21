import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Index, Computed
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.config import get_settings


class RawJob(Base):
    """Raw, untouched data exactly as it arrived from the source.
    Kept so we can reprocess without re-fetching."""

    __tablename__ = "raw_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # csv / adzuna / wwr
    source_job_id: Mapped[str | None] = mapped_column(String(255))   # ID from the source
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)      # entire raw record
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    __table_args__ = (
        Index("ix_raw_source_job", "source", "source_job_id", unique=True),
    )


class Job(Base):
    """Canonical job vacancy — the deduplicated, normalised representation.

    One canonical job may have multiple source postings (JobPosting records)
    from different platforms. This entity represents the "truth" after
    processing, deduplication, and normalisation.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    raw_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_jobs.id")
    )

    # ── Core fields ──
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_clean: Mapped[str | None] = mapped_column(String(500))
    company: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    description_clean: Mapped[str | None] = mapped_column(Text)  # Stripped of boilerplate
    requirements: Mapped[str | None] = mapped_column(Text)  # Extracted requirements
    responsibilities: Mapped[str | None] = mapped_column(Text)  # Extracted responsibilities

    # ── Location (structured) ──
    location_city: Mapped[str | None] = mapped_column(String(255))
    location_country: Mapped[str | None] = mapped_column(String(100))
    remote: Mapped[bool] = mapped_column(Boolean, default=False)

    # UK-specific location fields
    uk_country: Mapped[str | None] = mapped_column(String(50))  # England/Scotland/Wales/Northern Ireland
    uk_region: Mapped[str | None] = mapped_column(String(100))  # e.g. "South East", "North West"
    county: Mapped[str | None] = mapped_column(String(100))
    postcode_area: Mapped[str | None] = mapped_column(String(10))  # e.g. "SW1", "EC1"
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    # ── Workplace type ──
    workplace_type: Mapped[str | None] = mapped_column(String(50))  # remote/hybrid/onsite

    # ── Salary ──
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    salary_period: Mapped[str | None] = mapped_column(String(20))  # annual/monthly/hourly/daily
    original_salary_text: Mapped[str | None] = mapped_column(String(255))  # Raw salary text from source
    annualised_gbp_salary: Mapped[float | None] = mapped_column(Float)  # Normalised to GBP annual
    salary_confidence: Mapped[float | None] = mapped_column(Float)  # 0.0-1.0 extraction confidence

    # ── Classification ──
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    job_type: Mapped[str | None] = mapped_column(String(50))  # full-time/part-time/contract
    contract_duration: Mapped[str | None] = mapped_column(String(50))  # permanent/fixed-term/etc
    experience_level: Mapped[str | None] = mapped_column(String(50))

    # ── Meta ──
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    closing_date: Mapped[datetime | None] = mapped_column(DateTime)
    url: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    dedup_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # ── Quality score ──
    quality_score: Mapped[float | None] = mapped_column(Float)  # 0.0-1.0 data quality indicator

    # ── Full-text search ──
    search_vector = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title_clean, '') || ' ' || coalesce(description, ''))",
            persisted=True,
        ),
    )

    # ── Embedding metadata ──
    embedding = mapped_column(Vector(get_settings().embedding_dim), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))  # e.g. "BAAI/bge-base-en-v1.5"
    embedding_dim: Mapped[int | None] = mapped_column(Integer)  # e.g. 768
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime)
    source_text_hash: Mapped[str | None] = mapped_column(String(64))  # Hash of text used for embedding

    # ── Processing version ──
    processing_version: Mapped[str | None] = mapped_column(String(50))  # Pipeline version that produced this

    # ── Timestamps ──
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=datetime.utcnow)

    # ── Relationships ──
    skills: Mapped[list["JobSkill"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    postings: Mapped[list["JobPosting"]] = relationship(back_populates="canonical_job")  # noqa: F821


class JobSkill(Base):
    """Individual skill extracted from a job posting."""

    __tablename__ = "job_skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    skill: Mapped[str] = mapped_column(Text, nullable=False)

    # Skill metadata
    confidence: Mapped[float | None] = mapped_column(Float)  # Extraction confidence
    is_essential: Mapped[bool | None] = mapped_column(Boolean)  # Essential vs desirable
    extraction_method: Mapped[str | None] = mapped_column(String(50))  # dictionary/llm/hybrid

    job: Mapped["Job"] = relationship(back_populates="skills")

    __table_args__ = (
        Index("ix_job_skill_pair", "job_id", "skill", unique=True),
    )
