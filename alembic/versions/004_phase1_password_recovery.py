"""Add persistent reset-token blacklist.

Revision ID: 004_phase1_password_recovery
Revises: 003_search_infrastructure
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_phase1_password_recovery"
down_revision = "003_search_infrastructure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "token_blacklist",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("blacklisted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_jti"),
    )
    op.create_index("ix_token_blacklist_user_id", "token_blacklist", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_token_blacklist_user_id", table_name="token_blacklist")
    op.drop_table("token_blacklist")
