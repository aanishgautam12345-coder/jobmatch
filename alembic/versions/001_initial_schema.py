"""Initial schema — captures the complete JobMatch AI database structure.

This migration creates all tables for the JobMatch AI system including:
- Core entities: raw_jobs, jobs, job_skills, users, user_profiles
- Source tracking: job_postings
- Recommendations: recommendations, recommendation_runs, saved_jobs
- Notifications: notifications, notification_preferences
- Monitoring: ingestion_runs, processing_errors
- Interactions: user_interactions

Revision ID: 001_initial
Create Date: 2026-07-13
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── raw_jobs ──
    op.create_table(
        "raw_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_job_id", sa.String(255)),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("processed", sa.Boolean, server_default="false"),
    )
    op.create_index("ix_raw_source_job", "raw_jobs", ["source", "source_job_id"], unique=True)
    op.create_index("ix_raw_jobs_processed", "raw_jobs", ["processed"])

    # ── jobs (canonical vacancies) ──
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_jobs.id")),
        # Core fields
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("title_clean", sa.String(500)),
        sa.Column("company", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("description_clean", sa.Text),
        sa.Column("requirements", sa.Text),
        sa.Column("responsibilities", sa.Text),
        # Location
        sa.Column("location_city", sa.String(255)),
        sa.Column("location_country", sa.String(100)),
        sa.Column("remote", sa.Boolean, server_default="false"),
        # UK-specific location
        sa.Column("uk_country", sa.String(50)),
        sa.Column("uk_region", sa.String(100)),
        sa.Column("county", sa.String(100)),
        sa.Column("postcode_area", sa.String(10)),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        # Workplace type
        sa.Column("workplace_type", sa.String(50)),
        # Salary
        sa.Column("salary_min", sa.Float),
        sa.Column("salary_max", sa.Float),
        sa.Column("salary_currency", sa.String(10)),
        sa.Column("salary_period", sa.String(20)),
        sa.Column("original_salary_text", sa.String(255)),
        sa.Column("annualised_gbp_salary", sa.Float),
        sa.Column("salary_confidence", sa.Float),
        # Classification
        sa.Column("category", sa.String(100)),
        sa.Column("job_type", sa.String(50)),
        sa.Column("contract_duration", sa.String(50)),
        sa.Column("experience_level", sa.String(50)),
        # Meta
        sa.Column("posted_at", sa.DateTime),
        sa.Column("closing_date", sa.DateTime),
        sa.Column("url", sa.String(1000)),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("dedup_hash", sa.String(64)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        # Quality
        sa.Column("quality_score", sa.Float),
        # Embedding
        sa.Column("embedding", Vector(768)),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("embedding_dim", sa.Integer),
        sa.Column("embedded_at", sa.DateTime),
        sa.Column("source_text_hash", sa.String(64)),
        # Processing version
        sa.Column("processing_version", sa.String(50)),
        # Timestamps
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_jobs_category", "jobs", ["category"])
    op.create_index("ix_jobs_dedup_hash", "jobs", ["dedup_hash"], unique=True)
    op.create_index("ix_jobs_is_active", "jobs", ["is_active"])
    op.create_index("ix_jobs_source", "jobs", ["source"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])

    # ── job_skills ──
    op.create_table(
        "job_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float),
        sa.Column("is_essential", sa.Boolean),
        sa.Column("extraction_method", sa.String(50)),
    )
    op.create_index("ix_job_skills_job_id", "job_skills", ["job_id"])
    op.create_index("ix_job_skill_pair", "job_skills", ["job_id", "skill"], unique=True)

    # ── job_postings (source-specific postings) ──
    op.create_table(
        "job_postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_jobs.id", ondelete="SET NULL")),
        # Source identification
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_job_id", sa.String(255)),
        sa.Column("source_url", sa.String(1000)),
        # Original data
        sa.Column("original_title", sa.String(500)),
        sa.Column("original_description", sa.Text),
        sa.Column("original_location", sa.String(500)),
        sa.Column("original_salary_text", sa.String(255)),
        sa.Column("original_currency", sa.String(10)),
        sa.Column("original_company", sa.String(255)),
        sa.Column("payload", postgresql.JSONB),
        # Timestamps
        sa.Column("first_seen_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("posted_at", sa.DateTime),
        sa.Column("expires_at", sa.DateTime),
        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),
    )
    op.create_index("ix_posting_source_job", "job_postings", ["source", "source_job_id"], unique=True)
    op.create_index("ix_posting_canonical", "job_postings", ["canonical_job_id", "is_active"])

    # ── users ──
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── user_profiles ──
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("headline", sa.String(500)),
        sa.Column("skills", postgresql.ARRAY(sa.String)),
        sa.Column("experience_years", sa.Integer),
        sa.Column("experience_level", sa.String(50)),
        sa.Column("preferred_locations", postgresql.ARRAY(sa.String)),
        sa.Column("preferred_job_types", postgresql.ARRAY(sa.String)),
        sa.Column("min_salary", sa.Float),
        sa.Column("salary_currency", sa.String(10), server_default="USD"),
        sa.Column("career_interests", sa.Text),
        sa.Column("profile_embedding", Vector(768)),
    )

    # ── notification_preferences ──
    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("email_enabled", sa.Boolean, server_default="true"),
        sa.Column("min_match_score", sa.Float, server_default="0.70"),
        sa.Column("frequency", sa.String(20), server_default="daily"),
    )

    # ── recommendation_runs ──
    op.create_table(
        "recommendation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # Retrieval config
        sa.Column("retrieval_method", sa.String(50), nullable=False),
        sa.Column("candidate_pool_size", sa.Integer, server_default="0"),
        sa.Column("final_pool_size", sa.Integer, server_default="0"),
        # Model versions
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("embedding_dim", sa.Integer),
        sa.Column("reranker_model", sa.String(100)),
        # Scoring config
        sa.Column("scoring_config", postgresql.JSONB),
        # Performance
        sa.Column("latency_ms", sa.Float),
        # Agent decisions
        sa.Column("agent_decisions", postgresql.JSONB),
        # Timestamps
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime),
        # Status
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("error_message", sa.Text),
    )
    op.create_index("ix_rec_run_user", "recommendation_runs", ["user_id"])

    # ── recommendations ──
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        # Scoring
        sa.Column("match_score", sa.Float, nullable=False),
        sa.Column("rank", sa.Integer),
        sa.Column("score_breakdown", postgresql.JSONB),
        # Retrieval context
        sa.Column("retrieval_method", sa.String(50)),
        sa.Column("candidate_pool_position", sa.Integer),
        # Explanation
        sa.Column("explanation", sa.Text),
        # Audit
        sa.Column("recommendation_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendation_runs.id", ondelete="SET NULL")),
        # Timestamps
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_recommendations_user", "recommendations", ["user_id"])
    op.create_index("ix_recommendations_job", "recommendations", ["job_id"])

    # ── saved_jobs ──
    op.create_table(
        "saved_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("saved_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_saved_jobs_user", "saved_jobs", ["user_id"])
    op.create_index("ix_saved_jobs_job", "saved_jobs", ["job_id"])

    # ── notifications ──
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("match_score", sa.Float),
        sa.Column("sent_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("opened", sa.Boolean, server_default="false"),
    )
    op.create_index("ix_notifications_user", "notifications", ["user_id"])
    op.create_index("ix_notifications_job", "notifications", ["job_id"])

    # ── ingestion_runs ──
    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("records_fetched", sa.Integer, server_default="0"),
        sa.Column("records_inserted", sa.Integer, server_default="0"),
        sa.Column("records_skipped", sa.Integer, server_default="0"),
        sa.Column("errors", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("error_message", sa.Text),
    )

    # ── processing_errors ──
    op.create_table(
        "processing_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL")),
        sa.Column("raw_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_jobs.id", ondelete="SET NULL")),
        sa.Column("error_type", sa.String(100), nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column("stack_trace", sa.Text),
        sa.Column("source", sa.String(50)),
        sa.Column("source_job_id", sa.String(255)),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("resolved", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_proc_error_ingestion", "processing_errors", ["ingestion_run_id"])
    op.create_index("ix_proc_error_raw_job", "processing_errors", ["raw_job_id"])

    # ── user_interactions ──
    op.create_table(
        "user_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interaction_type", sa.String(50), nullable=False),
        sa.Column("metadata", postgresql.JSONB),
        sa.Column("source", sa.String(50)),
        sa.Column("recommendation_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendation_runs.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_interaction_user", "user_interactions", ["user_id"])
    op.create_index("ix_interaction_job", "user_interactions", ["job_id"])
    op.create_index("ix_interaction_type", "user_interactions", ["interaction_type"])


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("user_interactions")
    op.drop_table("processing_errors")
    op.drop_table("ingestion_runs")
    op.drop_table("notifications")
    op.drop_table("saved_jobs")
    op.drop_table("recommendations")
    op.drop_table("recommendation_runs")
    op.drop_table("notification_preferences")
    op.drop_table("user_profiles")
    op.drop_table("users")
    op.drop_table("job_postings")
    op.drop_table("job_skills")
    op.drop_table("jobs")
    op.drop_table("raw_jobs")
