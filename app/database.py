"""Database configuration for JobMatch AI.

Uses SQLAlchemy 2.0 with PostgreSQL + pgvector.

For development: init_db() creates all tables directly.
For production: Use Alembic migrations (alembic upgrade head).
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_engine(settings.database_url, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and enable pgvector extension.

    Note: This is for development/prototyping only. For production use
    Alembic migrations: `alembic upgrade head`
    """
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")


def run_migrations():
    """Run Alembic migrations. Requires alembic to be installed and configured."""
    import subprocess
    import sys

    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info(f"Migrations applied: {result.stdout}")
    except FileNotFoundError:
        logger.error("Alembic not found. Install with: pip install alembic")
    except subprocess.CalledProcessError as e:
        logger.error(f"Migration failed: {e.stderr}")
