"""Shared test fixtures for JobMatch AI.

Run all tests:
    python -m pytest tests/ -v

Run specific test file:
    python -m pytest tests/test_metrics.py -v
"""

import os
import sys
import uuid
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine
from app.models.user import User
from app.models.job import Job, RawJob
from app.models.recommendation import Recommendation, SavedJob
from app.models.recommendation_run import RecommendationRun
from app.models.user_interaction import UserInteraction
from app.services.scoring_config import ScoringWeights


# ── Database fixtures ──

@pytest.fixture(scope="session")
def test_engine():
    """Create an in-memory SQLite engine for the entire test session."""
    from sqlalchemy import create_engine
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db(test_engine):
    """Provide a transactional database session that rolls back after each test."""
    from sqlalchemy.orm import sessionmaker
    connection = test_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ── Model fixtures ──

@pytest.fixture()
def sample_user(db):
    """Create a sample user with profile."""
    from app.models.user import UserProfile
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        hashed_password="fakehash",
        is_active=True,
    )
    profile = UserProfile(
        user_id=user.id,
        skills=["python", "fastapi", "postgresql"],
        desired_roles=["backend developer"],
        locations=["London", "Remote"],
        experience_years=3,
        work_type="remote",
    )
    db.add_all([user, profile])
    db.flush()
    return user


@pytest.fixture()
def sample_jobs(db):
    """Create a batch of sample jobs for search/recommendation testing."""
    jobs = []
    titles = [
        ("Senior Python Developer", ["python", "fastapi", "postgresql"], "London", 65000),
        ("Data Scientist", ["python", "machine learning", "pandas"], "Manchester", 55000),
        ("Backend Engineer", ["python", "django", "aws"], "Remote", 70000),
        ("Junior Developer", ["python", "flask", "git"], "Birmingham", 28000),
        ("DevOps Engineer", ["python", "docker", "kubernetes"], "London", 75000),
    ]
    for title, skills, location, salary in titles:
        job = Job(
            id=uuid.uuid4(),
            title=title,
            title_clean=title.lower(),
            company=f"Test Company {uuid.uuid4().hex[:6]}",
            location=location,
            location_country="UK",
            description=f"We are looking for a {title} with experience in {', '.join(skills)}.",
            salary_min=salary,
            salary_max=salary + 10000,
            skills=skills,
            source="test",
            is_active=True,
            quality_score=80,
        )
        db.add(job)
        jobs.append(job)
    db.flush()
    return jobs


@pytest.fixture()
def sample_recommendation_run(db):
    """Create a sample recommendation run for audit trail testing."""
    run = RecommendationRun(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        queries_generated=2,
        candidate_pool_size=50,
        hard_filtered_count=10,
        final_recommendations=5,
        scoring_config={"semantic_weight": 0.4, "skills_weight": 0.3},
        agent_decisions=[
            {"step": "retrieve", "method": "hybrid", "count": 50},
            {"step": "score", "method": "weighted", "count": 50},
            {"step": "filter", "threshold": 0.3, "count": 40},
            {"step": "rerank", "method": "cross_encoder", "count": 5},
        ],
        latency_ms=1500,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


@pytest.fixture()
def default_weights():
    """Provide default scoring weights."""
    return ScoringWeights()
