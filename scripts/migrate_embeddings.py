"""Migrate embeddings from 384-dim (MiniLM) to 768-dim (BGE).

This script:
    1. Alters the vector columns in jobs and user_profiles from 384 to 768
    2. Clears all existing embeddings (they're incompatible with the new model)
    3. Triggers a full reprocess to generate new embeddings

Usage:
    python -m scripts.migrate_embeddings
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine
from app.config import get_settings
from sqlalchemy import text


def migrate():
    settings = get_settings()
    new_dim = settings.embedding_dim

    print(f"\n{'='*60}")
    print(f"  Migrating vector columns to {new_dim} dimensions")
    print(f"  Model: {settings.embedding_model}")
    print(f"{'='*60}\n")

    with engine.connect() as conn:
        # Drop the old HNSW indexes (they're dimension-specific)
        print("  Dropping old vector indexes ...")
        conn.execute(text("DROP INDEX IF EXISTS ix_jobs_embedding"))
        conn.execute(text("DROP INDEX IF EXISTS ix_user_profiles_profile_embedding"))

        # Alter the vector columns to the new dimension
        print(f"  Altering jobs.embedding → vector({new_dim}) ...")
        conn.execute(text(f"""
            ALTER TABLE jobs
            ALTER COLUMN embedding TYPE vector({new_dim})
            USING NULL
        """))

        print(f"  Altering user_profiles.profile_embedding → vector({new_dim}) ...")
        conn.execute(text(f"""
            ALTER TABLE user_profiles
            ALTER COLUMN profile_embedding TYPE vector({new_dim})
            USING NULL
        """))

        # Recreate HNSW indexes with new dimension
        print("  Recreating HNSW indexes ...")
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS ix_jobs_embedding
            ON jobs USING hnsw (embedding vector_cosine_ops)
        """))
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS ix_user_profiles_embedding
            ON user_profiles USING hnsw (profile_embedding vector_cosine_ops)
        """))

        # Mark all jobs as unprocessed so they get re-embedded
        print("  Clearing processed flags ...")
        conn.execute(text("UPDATE raw_jobs SET processed = false"))

        conn.commit()

    print(f"\n  ✓ Migration complete.")
    print(f"  Next step: python -m scripts.run_processing")
    print(f"  This will re-embed all jobs with the new {settings.embedding_model} model.\n")


if __name__ == "__main__":
    migrate()
