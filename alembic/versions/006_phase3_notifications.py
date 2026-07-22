"""Add truthful, idempotent notification delivery state.

Revision ID: 006_phase3_notifications
Revises: 005_phase2_administration
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_phase3_notifications"
down_revision = "005_phase2_administration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_preferences", sa.Column("timezone", sa.String(50), server_default="UTC", nullable=False))
    op.add_column("notification_preferences", sa.Column("last_processed_at", sa.DateTime(), nullable=True))
    op.add_column("notification_preferences", sa.Column("last_digest_sent_at", sa.DateTime(), nullable=True))
    op.create_check_constraint(
        "ck_notification_frequency", "notification_preferences",
        "frequency IN ('instant', 'daily', 'weekly')",
    )
    op.create_check_constraint(
        "ck_notification_match_score", "notification_preferences",
        "min_match_score >= 0 AND min_match_score <= 1",
    )

    op.add_column("notifications", sa.Column("status", sa.String(20), server_default="pending", nullable=False))
    op.add_column("notifications", sa.Column("attempted_at", sa.DateTime(), nullable=True))
    op.add_column("notifications", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column("notifications", sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(255), nullable=True))
    op.add_column("notifications", sa.Column("digest_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("notifications", sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.alter_column("notifications", "sent_at", existing_type=sa.DateTime(), nullable=True)
    op.execute("UPDATE notifications SET status='sent', dedupe_key=user_id::text || ':' || job_id::text || ':' || type WHERE sent_at IS NOT NULL")
    op.execute("""
        DELETE FROM notifications a USING notifications b
        WHERE a.dedupe_key = b.dedupe_key AND a.id > b.id
    """)
    op.alter_column("notifications", "dedupe_key", nullable=False)
    op.create_unique_constraint("uq_notifications_dedupe_key", "notifications", ["dedupe_key"])
    op.create_index("ix_notifications_digest_id", "notifications", ["digest_id"])
    op.create_check_constraint(
        "ck_notification_status", "notifications",
        "status IN ('pending', 'sent', 'failed')",
    )
    op.execute("""
        DELETE FROM saved_jobs a USING saved_jobs b
        WHERE a.user_id = b.user_id AND a.job_id = b.job_id AND a.id > b.id
    """)
    op.create_unique_constraint("uq_saved_jobs_user_job", "saved_jobs", ["user_id", "job_id"])


def downgrade() -> None:
    op.drop_constraint("uq_saved_jobs_user_job", "saved_jobs", type_="unique")
    op.drop_constraint("ck_notification_status", "notifications", type_="check")
    op.drop_index("ix_notifications_digest_id", table_name="notifications")
    op.drop_constraint("uq_notifications_dedupe_key", "notifications", type_="unique")
    for column in ("created_at", "digest_id", "dedupe_key", "retry_count", "failure_reason", "attempted_at", "status"):
        op.drop_column("notifications", column)
    op.execute("UPDATE notifications SET sent_at = CURRENT_TIMESTAMP WHERE sent_at IS NULL")
    op.alter_column("notifications", "sent_at", existing_type=sa.DateTime(), nullable=False)
    op.drop_constraint("ck_notification_match_score", "notification_preferences", type_="check")
    op.drop_constraint("ck_notification_frequency", "notification_preferences", type_="check")
    op.drop_column("notification_preferences", "last_digest_sent_at")
    op.drop_column("notification_preferences", "last_processed_at")
    op.drop_column("notification_preferences", "timezone")
