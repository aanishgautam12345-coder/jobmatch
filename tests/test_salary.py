"""Tests for salary parsing (Phase 2)."""

import pytest
from app.processing.salary import parse_salary, ParsedSalary


class TestParseSalary:
    def test_annual_range(self):
        result = parse_salary("£50,000 - £70,000 per annum")
        assert result is not None
        assert isinstance(result, ParsedSalary)
        assert result.min_salary == 50000
        assert result.max_salary == 70000

    def test_monthly(self):
        result = parse_salary("£3,500 per month")
        assert result is not None
        assert result.min_salary == 3500

    def test_hourly(self):
        result = parse_salary("£25 per hour")
        assert result is not None
        assert result.min_salary == 25

    def test_daily(self):
        result = parse_salary("£400 per day")
        assert result is not None
        assert result.min_salary == 400

    def test_single_value(self):
        result = parse_salary("£60,000")
        assert result is not None
        assert result.min_salary == 60000
        assert result.max_salary == 60000

    def test_competitive(self):
        result = parse_salary("Competitive salary")
        assert result is not None
        assert result.is_competitive is True

    def test_empty_returns_object(self):
        """parse_salary returns a ParsedSalary even for empty input."""
        result = parse_salary("")
        assert result is not None
        assert isinstance(result, ParsedSalary)

    def test_none_returns_object(self):
        result = parse_salary(None)
        assert result is not None

    def test_period_detected(self):
        result = parse_salary("£25 per hour")
        assert result.period == "hourly"

    def test_confidence_scored(self):
        result = parse_salary("£50,000 per annum")
        assert 0 <= result.confidence <= 1

    def test_usd_currency(self):
        result = parse_salary("$50,000 per year")
        assert result is not None
        assert result.min_salary == 50000

    def test_eur_currency(self):
        result = parse_salary("€45,000 per annum")
        assert result is not None
        assert result.min_salary == 45000
