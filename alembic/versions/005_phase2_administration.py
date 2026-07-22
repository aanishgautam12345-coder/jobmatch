"""Add administration, archival, and normalization support.

Revision ID: 005_phase2_administration
Revises: 004_phase1_password_recovery
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_phase2_administration"
down_revision = "004_phase1_password_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("raw_jobs", sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("raw_jobs", sa.Column("processing_attempts", sa.Integer(), server_default="0", nullable=False))
    op.create_foreign_key(
        "fk_raw_jobs_ingestion_run", "raw_jobs", "ingestion_runs",
        ["ingestion_run_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_raw_jobs_ingestion_run_id", "raw_jobs", ["ingestion_run_id"])
    op.create_table(
        "normalization_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("canonical_value", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("kind IN ('category', 'location')", name="ck_normalization_alias_kind"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_normalization_alias_kind_alias", "normalization_aliases",
        ["kind", "alias"], unique=True,
    )
    op.execute("""
        UPDATE jobs
        SET salary_min = LEAST(salary_min, salary_max),
            salary_max = GREATEST(salary_min, salary_max)
        WHERE salary_min IS NOT NULL AND salary_max IS NOT NULL
          AND salary_min > salary_max
    """)
    op.create_check_constraint(
        "ck_jobs_salary_range", "jobs",
        "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
    )


def downgrade() -> None:
    op.drop_constraint("ck_jobs_salary_range", "jobs", type_="check")
    op.drop_index("uq_normalization_alias_kind_alias", table_name="normalization_aliases")
    op.drop_table("normalization_aliases")
    op.drop_index("ix_raw_jobs_ingestion_run_id", table_name="raw_jobs")
    op.drop_constraint("fk_raw_jobs_ingestion_run", "raw_jobs", type_="foreignkey")
    op.drop_column("raw_jobs", "processing_attempts")
    op.drop_column("raw_jobs", "ingestion_run_id")
    op.drop_column("users", "is_admin")
