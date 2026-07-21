"""Tests for profile completeness scoring (Phase 4)."""

import pytest
import uuid
from app.services.profile_completeness import calculate_completeness, CompletenessResult
from app.models.user import UserProfile


def make_profile(**kwargs) -> UserProfile:
    """Create a UserProfile with sensible defaults for testing."""
    defaults = {
        "user_id": uuid.uuid4(),
        "headline": None,
        "skills": [],
        "experience_level": None,
        "preferred_locations": [],
        "min_salary": None,
        "preferred_job_types": [],
        "career_interests": [],
        "full_name": None,
        "experience_years": None,
    }
    defaults.update(kwargs)
    return UserProfile(**defaults)


class TestCalculateCompleteness:
    def test_empty_profile(self):
        profile = make_profile()
        result = calculate_completeness(profile)
        assert isinstance(result, CompletenessResult)
        assert result.overall == 0.0
        assert len(result.recommendations) > 0

    def test_full_profile(self):
        profile = make_profile(
            headline="Senior Python Developer",
            skills=["python", "fastapi"],
            experience_level="senior",
            preferred_locations=["London"],
            min_salary=50000,
            preferred_job_types=["remote"],
            career_interests=["backend"],
            full_name="Test User",
            experience_years=5,
        )
        result = calculate_completeness(profile)
        assert result.overall > 70.0

    def test_partial_profile(self):
        profile = make_profile(
            skills=["python"],
            experience_level="junior",
        )
        result = calculate_completeness(profile)
        assert 0 < result.overall < 100.0

    def test_score_in_range(self):
        profile = make_profile(
            headline="Developer",
            skills=["python", "fastapi"],
            experience_level="mid",
            preferred_locations=["London"],
            min_salary=40000,
            preferred_job_types=["remote"],
            career_interests=["backend"],
            full_name="Full Name",
            experience_years=3,
        )
        result = calculate_completeness(profile)
        assert 0 <= result.overall <= 100.0

    def test_has_recommendations(self):
        profile = make_profile()
        result = calculate_completeness(profile)
        assert isinstance(result.recommendations, list)

    def test_filled_fields_counted(self):
        profile = make_profile(skills=["python"], experience_level="junior")
        result = calculate_completeness(profile)
        assert result.filled_fields >= 2
