"""Tests for OpenAI LLM integration (RAG explanations + resume parsing).

All tests use mocks — no real API calls.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4

from app.services.rag import generate_explanation, _explanation_cache
from app.services.resume_parser import parse_resume_with_llm
from app.services.recommendation import MatchBreakdown


# ── Fixtures ──


@pytest.fixture()
def sample_profile():
    profile = MagicMock()
    profile.user_id = uuid4()
    profile.headline = "Senior Python Developer"
    profile.skills = ["python", "fastapi", "postgresql"]
    profile.experience_level = "senior"
    profile.experience_years = 6
    profile.preferred_locations = ["London", "Remote"]
    profile.min_salary = 60000
    profile.salary_currency = "GBP"
    return profile


@pytest.fixture()
def sample_job():
    job = MagicMock()
    job.id = uuid4()
    job.title = "Senior Backend Engineer"
    job.title_clean = "senior backend engineer"
    job.company = "Test Corp"
    job.location_city = "London"
    job.location_country = "UK"
    job.remote = False
    job.salary_min = 70000
    job.salary_max = 90000
    job.salary_currency = "GBP"
    job.category = "Engineering"
    return job


@pytest.fixture()
def sample_breakdown():
    return MatchBreakdown(
        match_percentage=85,
        semantic_similarity=0.82,
        skill_overlap=0.75,
        matching_skills=["python", "fastapi"],
        missing_skills=["aws"],
        location_fit=1.0,
        salary_fit=1.0,
        experience_fit=1.0,
    )


# ── Helpers ──


def _make_fake_response(output_text: str):
    fake = MagicMock()
    fake.output_text = output_text
    return fake


# ── Tests: Missing API Key ──


def test_generate_explanation_missing_key(sample_profile, sample_job, sample_breakdown):
    _explanation_cache.clear()
    with patch("app.services.rag.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = ""
        mock_settings.return_value.openai_model = "gpt-5.6-sol"
        result = generate_explanation(sample_profile, sample_job, sample_breakdown)
        assert "scored" in result
        assert "85%" in result


def test_parse_resume_missing_key():
    with patch("app.services.resume_parser.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = ""
        with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
            parse_resume_with_llm("fake resume text")


# ── Tests: Successful Explanation ──


@patch("app.services.rag._get_client")
def test_generate_explanation_success(mock_get_client, sample_profile, sample_job, sample_breakdown):
    _explanation_cache.clear()
    fake_client = MagicMock()
    fake_client.responses.create.return_value = _make_fake_response(
        "This role matches your senior Python skills. Your experience aligns with the required tech stack. The location and salary fit your preferences."
    )
    mock_get_client.return_value = fake_client

    result = generate_explanation(sample_profile, sample_job, sample_breakdown, validate=False)
    assert "matches" in result
    assert "Python" in result


@patch("app.services.rag._get_client")
def test_generate_explanation_caches(mock_get_client, sample_profile, sample_job, sample_breakdown):
    _explanation_cache.clear()
    fake_client = MagicMock()
    fake_client.responses.create.return_value = _make_fake_response("Cached explanation text.")
    mock_get_client.return_value = fake_client

    result1 = generate_explanation(sample_profile, sample_job, sample_breakdown, validate=False)
    result2 = generate_explanation(sample_profile, sample_job, sample_breakdown, validate=False)

    assert result1 == result2
    assert fake_client.responses.create.call_count == 1


# ── Tests: API Failure / Rate-Limit Fallback ──


@patch("app.services.rag._get_client")
def test_generate_explanation_api_error_fallback(mock_get_client, sample_profile, sample_job, sample_breakdown):
    _explanation_cache.clear()
    fake_client = MagicMock()
    fake_client.responses.create.side_effect = Exception("Rate limit exceeded")
    mock_get_client.return_value = fake_client

    result = generate_explanation(sample_profile, sample_job, sample_breakdown)
    assert "85%" in result


# ── Tests: Invalid / Empty Output ──


@patch("app.services.rag._get_client")
def test_generate_explanation_empty_output(mock_get_client, sample_profile, sample_job, sample_breakdown):
    _explanation_cache.clear()
    fake_client = MagicMock()
    fake_client.responses.create.return_value = _make_fake_response("")
    mock_get_client.return_value = fake_client

    result = generate_explanation(sample_profile, sample_job, sample_breakdown, validate=False)
    assert result == ""


# ── Tests: Explanation Validation Still Executes ──


@patch("app.services.rag._get_client")
@patch("app.services.rag.validate_explanation")
def test_explanation_validation_called(mock_validate, mock_get_client, sample_profile, sample_job, sample_breakdown):
    _explanation_cache.clear()
    fake_client = MagicMock()
    fake_client.responses.create.return_value = _make_fake_response("Valid explanation text.")
    mock_get_client.return_value = fake_client

    mock_result = MagicMock()
    mock_result.is_valid = True
    mock_result.confidence = 0.9
    mock_result.issues = []
    mock_validate.return_value = mock_result

    generate_explanation(sample_profile, sample_job, sample_breakdown, validate=True)
    mock_validate.assert_called_once()


# ── Tests: Successful Resume Parsing ──


@patch("app.services.resume_parser.get_settings")
@patch("app.services.resume_parser.OpenAI")
def test_parse_resume_success(mock_openai, mock_get_settings):
    mock_settings = MagicMock()
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-5.6-sol"
    mock_get_settings.return_value = mock_settings
    valid_json = json.dumps({
        "full_name": "John Doe",
        "headline": "Senior Python Developer",
        "email": "john@example.com",
        "phone": "+1234567890",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "experience_years": 6,
        "experience_level": "senior",
        "preferred_locations": ["London"],
        "education": "MSc Computer Science",
        "career_interests": "Backend development",
        "work_history": [{"title": "Developer", "company": "Acme", "duration": "2020-2023"}],
    })

    fake_response = MagicMock()
    fake_response.output_text = valid_json

    fake_client = MagicMock()
    fake_client.responses.create.return_value = fake_response
    mock_openai.return_value = fake_client

    result = parse_resume_with_llm("John Doe resume text with Python skills")

    assert result["full_name"] == "John Doe"
    assert result["headline"] == "Senior Python Developer"
    assert "python" in result["skills"]
    assert result["experience_years"] == 6
    assert result["experience_level"] == "senior"


# ── Tests: Resume Parse — Malformed Output ──


@patch("app.services.resume_parser.get_settings")
@patch("app.services.resume_parser.OpenAI")
def test_parse_resume_malformed_json(mock_openai, mock_get_settings):
    mock_settings = MagicMock()
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-5.6-sol"
    mock_get_settings.return_value = mock_settings
    fake_response = MagicMock()
    fake_response.output_text = "not valid json at all"

    fake_client = MagicMock()
    fake_client.responses.create.return_value = fake_response
    mock_openai.return_value = fake_client

    with pytest.raises(ValueError, match="LLM returned invalid JSON"):
        parse_resume_with_llm("Some resume text")


# ── Tests: Resume Parse — API Failure ──


@patch("app.services.resume_parser.get_settings")
@patch("app.services.resume_parser.OpenAI")
def test_parse_resume_api_error(mock_openai, mock_get_settings):
    mock_settings = MagicMock()
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_model = "gpt-5.6-sol"
    mock_get_settings.return_value = mock_settings
    fake_client = MagicMock()
    fake_client.responses.create.side_effect = Exception("API unavailable")
    mock_openai.return_value = fake_client

    with pytest.raises(Exception, match="API unavailable"):
        parse_resume_with_llm("Some resume text")


# ── Tests: Response uses output_text attribute ──


@patch("app.services.rag._get_client")
def test_explanation_uses_output_text(mock_get_client, sample_profile, sample_job, sample_breakdown):
    _explanation_cache.clear()
    fake_client = MagicMock()
    fake_client.responses.create.return_value = _make_fake_response("Output from responses API")
    mock_get_client.return_value = fake_client

    result = generate_explanation(sample_profile, sample_job, sample_breakdown, validate=False)
    assert result == "Output from responses API"
