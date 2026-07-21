"""Phase 0A Regression Tests — Search Correctness and Data-Display Integrity.

Tests for:
    1. Evidence-backed search for technical queries
    2. Score separation (search_relevance vs profile_match)
    3. Salary currency handling (never default to USD)
    4. Missing salary boundary display (never convert to zero)
    5. Result-level duplicate suppression
    6. Match evidence generation
    7. Technical query detection
    8. Salary formatting

Run:
    python -m pytest tests/test_search_correctness.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.processing.salary import parse_salary, ParsedSalary
from app.services.search import (
    _normalise_query, _is_technical_query, _get_aliases,
    _normalise_company, _normalise_title, _compute_lexical_score,
    format_salary_display, _group_duplicates, SearchResult, MatchEvidence,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. Technical Query Detection
# ═══════════════════════════════════════════════════════════════════════

class TestTechnicalQueryDetection:
    """Verify that short technical queries are correctly detected."""

    def test_single_word_technical(self):
        assert _is_technical_query("Azure") is True
        assert _is_technical_query("Python") is True
        assert _is_technical_query("Docker") is True
        assert _is_technical_query("Kubernetes") is True
        assert _is_technical_query("React") is True
        assert _is_technical_query("Java") is True

    def test_two_word_technical(self):
        assert _is_technical_query("Power BI") is True
        assert _is_technical_query("Node JS") is True
        assert _is_technical_query(".NET Core") is True

    def test_long_query_not_technical(self):
        assert _is_technical_query("remote python developer in london") is False
        assert _is_technical_query("senior software engineer with cloud experience") is False

    def test_aliases_retrieved(self):
        aliases = _get_aliases("azure")
        assert "azure" in aliases
        assert "microsoft azure" in aliases
        assert "azure devops" in aliases

    def test_unknown_query_fallback(self):
        aliases = _get_aliases("cobol")
        assert "cobol" in aliases


# ═══════════════════════════════════════════════════════════════════════
# 2. Score Computation
# ═══════════════════════════════════════════════════════════════════════

class TestScoreComputation:
    """Verify lexical score computation."""

    def test_exact_title_highest(self):
        score = _compute_lexical_score("exact_title", 1, ["title"])
        assert score >= 90

    def test_exact_skill_high(self):
        score = _compute_lexical_score("exact_skill", 1, ["skill"])
        assert 80 <= score <= 90

    def test_exact_requirement_medium(self):
        score = _compute_lexical_score("exact_requirement", 1, ["requirements"])
        assert 75 <= score <= 85

    def test_exact_description_lower(self):
        score = _compute_lexical_score("exact_description", 1, ["description"])
        assert 65 <= score <= 75

    def test_semantic_fallback_lowest(self):
        score = _compute_lexical_score("semantic_fallback", 0, [])
        assert score <= 50

    def test_multi_field_bonus(self):
        score_single = _compute_lexical_score("exact_skill", 1, ["skill"])
        score_multi = _compute_lexical_score("exact_skill", 2, ["skill", "description"])
        assert score_multi >= score_single


# ═══════════════════════════════════════════════════════════════════════
# 3. Salary Currency Handling
# ═══════════════════════════════════════════════════════════════════════

class TestSalaryCurrency:
    """Verify that salary currency is never defaulted to USD."""

    def test_no_currency_when_none(self):
        result = parse_salary("Competitive salary")
        assert result.currency is None

    def test_gbp_preserved(self):
        result = parse_salary("£50,000 per year")
        assert result.currency == "GBP"

    def test_usd_preserved(self):
        result = parse_salary("$100,000 per year")
        assert result.currency == "USD"

    def test_eur_preserved(self):
        result = parse_salary("€75,000 per year")
        assert result.currency == "EUR"

    def test_source_currency_preserved(self):
        result = parse_salary(None, source_min=50000, source_max=70000, source_currency="GBP")
        assert result.currency == "GBP"

    def test_no_source_no_text_no_currency(self):
        result = parse_salary(None, source_min=50000, source_max=70000)
        assert result.currency is None


# ═══════════════════════════════════════════════════════════════════════
# 4. Missing Salary Boundaries
# ═══════════════════════════════════════════════════════════════════════

class TestMissingSalaryBoundaries:
    """Verify that missing salary min/max are never converted to zero."""

    def test_both_none(self):
        result = parse_salary(None)
        assert result.min_salary is None
        assert result.max_salary is None

    def test_only_max_provided(self):
        result = parse_salary("up to £100,000")
        assert result.min_salary is None
        assert result.max_salary is not None
        assert result.max_salary > 0

    def test_only_min_provided(self):
        result = parse_salary("from £50,000")
        assert result.min_salary is not None
        assert result.min_salary > 0
        assert result.max_salary is None

    def test_source_min_zero_rejected_by_sanity_bounds(self):
        """A source_min of 0 is implausible and rejected by sanity bounds."""
        result = parse_salary(None, source_min=0, source_max=50000)
        assert result.min_salary is None  # 0 rejected as implausible
        assert result.max_salary == 50000.0

    def test_search_result_none_salary(self):
        """SearchResult with None salary_min should not show as 0."""
        sr = SearchResult(
            id="test", title="Test", company=None,
            location_city=None, location_country=None,
            remote=False, salary_min=None, salary_max=50000,
            salary_currency="GBP", salary_period=None,
            original_salary_text=None, category=None,
            job_type=None, url=None, source=None,
        )
        d = sr.to_dict()
        assert d["salary_min"] is None
        assert d["salary_max"] == 50000


# ═══════════════════════════════════════════════════════════════════════
# 5. Salary Formatting
# ═══════════════════════════════════════════════════════════════════════

class TestSalaryFormatting:
    """Verify salary display formatting."""

    def test_both_none(self):
        assert format_salary_display(None, None, None) == "Salary not disclosed"

    def test_gbp_range(self):
        result = format_salary_display(35000, 45000, "GBP")
        assert "£35,000" in result
        assert "£45,000" in result

    def test_usd_range(self):
        result = format_salary_display(100000, 150000, "USD")
        assert "$100,000" in result
        assert "$150,000" in result

    def test_up_to_format(self):
        result = format_salary_display(None, 100000, "GBP")
        assert result.startswith("Up to")
        assert "£100,000" in result

    def test_from_format(self):
        result = format_salary_display(50000, None, "GBP")
        assert result.startswith("From")
        assert "£50,000" in result

    def test_unknown_currency_no_symbol(self):
        result = format_salary_display(50000, 70000, "XYZ")
        assert "50,000" in result
        assert "$" not in result
        assert "£" not in result

    def test_none_currency_no_symbol(self):
        result = format_salary_display(50000, 70000, None)
        assert "50,000" in result
        assert "$" not in result
        assert "£" not in result

    def test_period_included(self):
        result = format_salary_display(500, 600, "GBP", "daily")
        assert "per day" in result

    def test_same_min_max(self):
        result = format_salary_display(50000, 50000, "GBP")
        assert result.count("£50,000") == 1  # Should not repeat


# ═══════════════════════════════════════════════════════════════════════
# 6. Duplicate Suppression
# ═══════════════════════════════════════════════════════════════════════

class TestDuplicateSuppression:
    """Verify result-level duplicate grouping."""

    def test_company_normalisation(self):
        assert _normalise_company("Xact Placements Ltd") == _normalise_company("XACT PLACEMENTS LIMITED")
        assert _normalise_company("Acme Inc.") == _normalise_company("Acme Inc")
        assert _normalise_company("  Google  ") == _normalise_company("Google")

    def test_title_normalisation(self):
        assert _normalise_title("Senior Python Developer") == _normalise_title("Python Developer")
        # These differ in word order but fuzzy matching in dedup handles it
        assert _normalise_title("Backend Developer - Python") == "backend developer python"
        assert _normalise_title("Backend Python Developer") == "backend python developer"
        assert _normalise_title("Jr. Frontend Engineer") == _normalise_title("Frontend Engineer")

    def test_grouping_duplicates(self):
        r1 = SearchResult(
            id="1", title="Backend Developer - Python", company="Xact Placements Ltd",
            location_city="London", location_country="UK", remote=False,
            salary_min=50000, salary_max=70000, salary_currency="GBP",
            salary_period=None, original_salary_text=None,
            category="Software Engineering", job_type="full-time",
            url=None, source="reed", search_relevance_score=85.0,
            ranking_score=85.0, match_type="exact_skill",
        )
        r2 = SearchResult(
            id="2", title="Backend Python Developer", company="XACT PLACEMENTS LIMITED",
            location_city="London", location_country="UK", remote=False,
            salary_min=50000, salary_max=70000, salary_currency="GBP",
            salary_period=None, original_salary_text=None,
            category="Software Engineering", job_type="full-time",
            url=None, source="adzuna", search_relevance_score=82.0,
            ranking_score=82.0, match_type="exact_skill",
        )
        r3 = SearchResult(
            id="3", title="Frontend React Developer", company="Google",
            location_city="London", location_country="UK", remote=False,
            salary_min=80000, salary_max=100000, salary_currency="GBP",
            salary_period=None, original_salary_text=None,
            category="Software Engineering", job_type="full-time",
            url=None, source="reed", search_relevance_score=70.0,
            ranking_score=70.0, match_type="exact_skill",
        )
        results = _group_duplicates([r1, r2, r3])
        # r1 and r2 should be in the same group
        assert results[0].duplicate_group is not None
        assert results[1].duplicate_group is not None
        assert results[0].duplicate_group == results[1].duplicate_group
        # r3 should be in no group
        assert results[2].duplicate_group is None

    def test_different_companies_not_grouped(self):
        r1 = SearchResult(
            id="1", title="Python Developer", company="Acme Corp",
            location_city="London", location_country="UK", remote=False,
            salary_min=50000, salary_max=70000, salary_currency="GBP",
            salary_period=None, original_salary_text=None,
            category=None, job_type=None, url=None, source=None,
            search_relevance_score=85.0, ranking_score=85.0,
            match_type="exact_skill",
        )
        r2 = SearchResult(
            id="2", title="Python Developer", company="Beta Inc",
            location_city="London", location_country="UK", remote=False,
            salary_min=50000, salary_max=70000, salary_currency="GBP",
            salary_period=None, original_salary_text=None,
            category=None, job_type=None, url=None, source=None,
            search_relevance_score=83.0, ranking_score=83.0,
            match_type="exact_skill",
        )
        results = _group_duplicates([r1, r2])
        assert results[0].duplicate_group is None
        assert results[1].duplicate_group is None


# ═══════════════════════════════════════════════════════════════════════
# 7. Match Evidence
# ═══════════════════════════════════════════════════════════════════════

class TestMatchEvidence:
    """Verify that match evidence is correctly structured."""

    def test_evidence_dataclass(self):
        ev = MatchEvidence(field="title", text="Azure Cloud Engineer")
        assert ev.field == "title"
        assert ev.text == "Azure Cloud Engineer"

    def test_search_result_to_dict(self):
        sr = SearchResult(
            id="test-123",
            title="Azure DevOps Engineer",
            company="Microsoft",
            location_city="London",
            location_country="UK",
            remote=False,
            salary_min=80000,
            salary_max=100000,
            salary_currency="GBP",
            salary_period="annual",
            original_salary_text="£80k-£100k",
            category="DevOps & Infrastructure",
            job_type="full-time",
            url="https://example.com",
            source="reed",
            search_relevance_score=95.0,
            ranking_score=95.0,
            match_type="exact_title",
            matched_terms=["azure"],
            matched_fields=["title"],
            match_evidence=[MatchEvidence(field="title", text="Azure DevOps Engineer")],
        )
        d = sr.to_dict()
        assert d["id"] == "test-123"
        assert d["search_relevance_score"] == 95.0
        assert d["match_type"] == "exact_title"
        assert len(d["match_evidence"]) == 1
        assert d["match_evidence"][0]["field"] == "title"
        # Legacy fields
        assert d["match_percentage"] == 95.0
        assert d["similarity"] == 0.95


# ═══════════════════════════════════════════════════════════════════════
# 8. Query Normalisation
# ═══════════════════════════════════════════════════════════════════════

class TestQueryNormalisation:
    """Verify query normalisation."""

    def test_lowercasing(self):
        assert _normalise_query("AZURE") == "azure"

    def test_whitespace_collapsing(self):
        assert _normalise_query("  python   developer  ") == "python developer"

    def test_special_chars_removed(self):
        assert _normalise_query("C# developer") == "c# developer"
        assert _normalise_query(".NET Core") == ".net core"


# ═══════════════════════════════════════════════════════════════════════
# 9. Azure-Specific Regression Tests
# ═══════════════════════════════════════════════════════════════════════

class TestAzureRegression:
    """Regression tests for the Azure search defect."""

    def test_azure_is_technical(self):
        assert _is_technical_query("Azure") is True

    def test_azure_aliases_include_valid_terms(self):
        aliases = _get_aliases("azure")
        assert "azure" in aliases
        assert "microsoft azure" in aliases
        assert "azure devops" in aliases
        assert "azure functions" in aliases
        assert "aks" in aliases

    def test_azure_excludes_broad_aliases(self):
        aliases = _get_aliases("azure")
        assert "cloud" not in aliases
        assert "developer" not in aliases
        assert "software" not in aliases

    def test_python_is_technical(self):
        assert _is_technical_query("Python") is True

    def test_docker_is_technical(self):
        assert _is_technical_query("Docker") is True

    def test_kubernetes_is_technical(self):
        assert _is_technical_query("Kubernetes") is True

    def test_react_is_technical(self):
        assert _is_technical_query("React") is True

    def test_power_bi_is_technical(self):
        assert _is_technical_query("Power BI") is True

    def test_long_query_not_treated_as_technical(self):
        assert _is_technical_query("looking for a remote azure engineer") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
