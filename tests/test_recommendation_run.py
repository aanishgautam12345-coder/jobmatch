"""Tests for recommendation run audit trail (Phase 5).

Note: RecommendationRun uses JSONB (PostgreSQL-specific). These tests
validate the model definition structure, not database behavior.
Database-level JSONB tests require PostgreSQL.
"""

import pytest
from datetime import datetime, timezone
from app.models.recommendation_run import RecommendationRun


class TestRecommendationRun:
    def test_model_has_required_columns(self):
        """Verify the model defines all expected columns."""
        columns = {c.name for c in RecommendationRun.__table__.columns}
        expected = {
            "id", "user_id", "retrieval_method", "candidate_pool_size",
            "final_pool_size", "scoring_config", "latency_ms",
            "agent_decisions", "started_at", "completed_at", "status",
        }
        assert expected.issubset(columns)

    def test_scoring_config_column_type(self):
        """Verify scoring_config is JSONB."""
        from sqlalchemy.dialects.postgresql import JSONB
        col = RecommendationRun.__table__.c.scoring_config
        assert isinstance(col.type, JSONB)

    def test_agent_decisions_column_type(self):
        """Verify agent_decisions is JSONB."""
        from sqlalchemy.dialects.postgresql import JSONB
        col = RecommendationRun.__table__.c.agent_decisions
        assert isinstance(col.type, JSONB)

    def test_default_status(self):
        """Verify default status is 'running'."""
        col = RecommendationRun.__table__.c.status
        assert col.default.arg == "running"
