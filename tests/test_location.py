"""Tests for UK location processing (Phase 2)."""

import pytest
from app.processing.location import (
    UK_REGIONS,
    UK_COUNTIES,
    POSTCODE_AREAS,
    normalise_location,
)


class TestNormaliseLocation:
    def test_empty_input(self):
        result = normalise_location("")
        assert isinstance(result, dict)
        assert result["city"] is None

    def test_none_input(self):
        result = normalise_location(None)
        assert isinstance(result, dict)

    def test_returns_dict(self):
        result = normalise_location("London")
        assert isinstance(result, dict)
        assert "city" in result
        assert "country" in result
        assert "uk_country" in result
        assert "uk_region" in result
        assert "remote" in result
        assert "workplace_type" in result

    def test_london_detected(self):
        result = normalise_location("London")
        assert result["city"] == "London"

    def test_unknown_location(self):
        result = normalise_location("atlantis")
        assert result["city"] == "atlantis"


class TestDataStructures:
    def test_uk_regions_non_empty(self):
        assert len(UK_REGIONS) > 0

    def test_uk_counties_non_empty(self):
        assert len(UK_COUNTIES) > 0

    def test_postcode_areas_non_empty(self):
        assert len(POSTCODE_AREAS) > 0
