"""Tests for evaluation metrics (Phase 7)."""

import pytest
from app.evaluation.metrics import (
    precision_at_k,
    graded_precision_at_k,
    recall_at_k,
    mean_reciprocal_rank,
    average_precision,
    dcg_at_k,
    ndcg_at_k,
    evaluate_ranking,
)


class TestPrecisionAtK:
    def test_all_relevant(self):
        assert precision_at_k([1, 1, 1], 3) == 1.0

    def test_none_relevant(self):
        assert precision_at_k([0, 0, 0], 3) == 0.0

    def test_partial(self):
        assert precision_at_k([1, 0, 1], 3) == pytest.approx(2 / 3)

    def test_k_exceeds_length_uses_k_denominator(self):
        """Standard IR: k is fixed denominator even if list is shorter.
        [1, 0] has 1 relevant item, k=5 -> 1/5 = 0.2
        """
        assert precision_at_k([1, 0], 5) == 0.2

    def test_graded_uses_binary_threshold(self):
        """Graded relevance > 0 treated as relevant."""
        assert precision_at_k([3, 0, 2, 1, 0], 5) == pytest.approx(3 / 5)


class TestGradedPrecisionAtK:
    def test_all_high_relevance(self):
        assert graded_precision_at_k([3, 3, 3], 3) == 1.0

    def test_all_zero(self):
        assert graded_precision_at_k([0, 0, 0], 3) == 0.0

    def test_mixed_relevance(self):
        # [3, 1, 0] -> sum=4, max_possible=9 (3*3)
        result = graded_precision_at_k([3, 1, 0], 3)
        assert result == pytest.approx(4 / 9)

    def test_k_exceeds_length(self):
        result = graded_precision_at_k([3, 0], 5)
        assert result == pytest.approx(3 / 15)  # 3 / (3*5)


class TestRecallAtK:
    def test_finds_all_relevant(self):
        assert recall_at_k([1, 1, 1, 0, 0], 5, 3) == 1.0

    def test_finds_some(self):
        assert recall_at_k([1, 0, 0, 1, 0], 5, 3) == pytest.approx(2 / 3)

    def test_k_smaller_than_total_relevant(self):
        assert recall_at_k([1, 1, 0, 0, 0], 3, 4) == pytest.approx(2 / 4)


class TestMRR:
    def test_first_relevant(self):
        assert mean_reciprocal_rank([3, 0, 0]) == 1.0

    def test_second_relevant(self):
        assert mean_reciprocal_rank([0, 2, 0]) == 0.5

    def test_third_relevant(self):
        assert mean_reciprocal_rank([0, 0, 3]) == pytest.approx(1 / 3)

    def test_no_relevant(self):
        assert mean_reciprocal_rank([0, 0, 0]) == 0.0

    def test_multiple_relevant_uses_first(self):
        assert mean_reciprocal_rank([0, 1, 1]) == 0.5


class TestDCG:
    def test_perfect_ranking(self):
        dcg = dcg_at_k([3, 3, 3], 3)
        # Formula: sum((2^rel - 1) / log2(i + 2)) for i in 0..k-1
        # i=0: (2^3-1)/log2(2) = 7/1 = 7
        # i=1: (2^3-1)/log2(3) = 7/1.585 = 4.417
        # i=2: (2^3-1)/log2(4) = 7/2 = 3.5
        # Total = 14.917
        assert dcg == pytest.approx(14.917, abs=0.01)

    def test_empty(self):
        assert dcg_at_k([], 5) == 0.0

    def test_single_item(self):
        assert dcg_at_k([2], 1) == pytest.approx(3.0)  # (2^2-1)/1


class TestNDCG:
    def test_perfect(self):
        assert ndcg_at_k([3, 3, 3], 3) == pytest.approx(1.0)

    def test_empty(self):
        assert ndcg_at_k([], 5) == 0.0


class TestEvaluateRanking:
    def test_returns_all_keys(self):
        result = evaluate_ranking([3, 2, 1, 0, 0], k=5)
        expected_keys = {
            "precision_at_k", "graded_precision_at_k", "average_precision",
            "mrr", "ndcg_at_k", "num_relevant_found", "total_graded_score",
            "num_judged",
        }
        assert set(result.keys()) == expected_keys

    def test_num_relevant_found(self):
        result = evaluate_ranking([1, 0, 1, 0, 1], k=5)
        assert result["num_relevant_found"] == 3

    def test_total_graded_score(self):
        result = evaluate_ranking([3, 2, 1], k=3)
        assert result["total_graded_score"] == 6
