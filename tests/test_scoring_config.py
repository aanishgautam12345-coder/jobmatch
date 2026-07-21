"""Tests for scoring configuration (Phase 4)."""

import pytest
from app.services.scoring_config import ScoringWeights, ABLATION_WEIGHTS


class TestScoringWeights:
    def test_default_values(self):
        w = ScoringWeights()
        assert w.semantic == 0.40
        assert w.skills == 0.20
        assert w.location == 0.15
        assert w.salary == 0.10
        assert w.experience == 0.10
        assert w.job_type == 0.05

    def test_weights_sum_to_one(self):
        w = ScoringWeights()
        total = w.semantic + w.skills + w.location + w.salary + w.experience + w.job_type
        assert total == pytest.approx(1.0)

    def test_custom_values(self):
        w = ScoringWeights(
            semantic=0.5,
            skills=0.25,
            location=0.05,
            salary=0.05,
            experience=0.05,
            job_type=0.10,
        )
        assert w.semantic == 0.5
        total = w.semantic + w.skills + w.location + w.salary + w.experience + w.job_type
        assert total == pytest.approx(1.0)

    def test_to_dict(self):
        w = ScoringWeights()
        d = w.to_dict()
        assert isinstance(d, dict)
        assert "semantic" in d
        assert d["semantic"] == 0.40

    def test_from_dict(self):
        d = {
            "semantic": 0.5,
            "skills": 0.25,
            "location": 0.05,
            "salary": 0.05,
            "experience": 0.05,
            "job_type": 0.10,
        }
        w = ScoringWeights.from_dict(d)
        assert w.semantic == 0.5
        assert w.skills == 0.25

    def test_from_dict_ignores_unknown_keys(self):
        d = {
            "semantic": 0.5,
            "skills": 0.25,
            "location": 0.05,
            "salary": 0.05,
            "experience": 0.05,
            "job_type": 0.10,
            "unknown_key": 999,
        }
        w = ScoringWeights.from_dict(d)
        assert w.semantic == 0.5

    def test_ablation_configs_exist(self):
        assert "semantic_only" in ABLATION_WEIGHTS
        assert "skills_only" in ABLATION_WEIGHTS
        assert "no_semantic" in ABLATION_WEIGHTS
        assert "balanced" in ABLATION_WEIGHTS

    def test_semantic_only_weights(self):
        w = ABLATION_WEIGHTS["semantic_only"]
        assert w.semantic == 1.0
        assert w.skills == 0.0

    def test_skills_only_weights(self):
        w = ABLATION_WEIGHTS["skills_only"]
        assert w.skills == 1.0
        assert w.semantic == 0.0
