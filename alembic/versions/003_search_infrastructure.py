"""Phase 3 — Search infrastructure: HNSW index, full-text search, reranker support.

Adds:
- HNSW index on jobs.embedding for approximate nearest neighbor search
- search_vector (tsvector) column on jobs for PostgreSQL full-text search
- GIN index on search_vector for fast tsquery matching
- Updates embedding model metadata

Revision ID: 003_search_infrastructure
Create Date: 2026-07-13
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_search_infrastructure"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── HNSW index on embedding column ──
    # HNSW provides O(log n) approximate nearest neighbor search
    # vs the default flat index which is O(n) exact search
    # Parameters: m=16 (connections per node), ef_construction=64 (build quality)
    op.execute("""
        CREATE INDEX ix_jobs_embedding_hnsw
        ON jobs
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # ── Full-text search vector column ──
    # Computed tsvector from title_clean + description using English dictionary
    op.add_column(
        "jobs",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(title_clean, '') || ' ' || coalesce(description, ''))",
                persisted=True,
            ),
        ),
    )

    # ── GIN index on search_vector ──
    # GIN is the standard index type for tsvector columns
    # Enables fast @@ tsquery matching
    op.execute("""
        CREATE INDEX ix_jobs_search_vector
        ON jobs
        USING gin (search_vector)
    """)


def downgrade() -> None:
    op.drop_index("ix_jobs_search_vector", table_name="jobs")
    op.drop_column("jobs", "search_vector")
    op.drop_index("ix_jobs_embedding_hnsw", table_name="jobs")
