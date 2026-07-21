"""Information Retrieval Evaluation Metrics.

Standard metrics for comparing ranked search results against human
relevance judgments. Used to compare Semantic Search vs Keyword Search
(and later, the Recommendation Agent) — this IS your dissertation's
evaluation methodology in code.

All functions take a `relevance` list: a list of integers in RANK ORDER
(relevance[0] = judgment for the #1 result).

Graded relevance scale:
    0 = Not relevant
    1 = Partially relevant (tangentially related)
    2 = Relevant (genuinely useful match)
    3 = Highly relevant (strong, precise match)

Binary functions treat any relevance > 0 as relevant.
Graded functions use the full 0-3 scale.
"""

import math


def precision_at_k(relevance: list[int], k: int) -> float:
    """Precision@k = (# relevant in top k) / k.

    Binary: counts any relevance > 0 as relevant.
    """
    if k <= 0:
        return 0.0
    top_k = relevance[:k]
    return sum(1 for r in top_k if r > 0) / k


def graded_precision_at_k(relevance: list[int], k: int) -> float:
    """Graded Precision@k — average relevance score in top k, normalised to [0,1].

    Uses the full 0-3 scale.
    """
    if k <= 0:
        return 0.0
    top_k = relevance[:k]
    return sum(top_k) / (k * 3)


def recall_at_k(relevance: list[int], k: int, total_relevant: int) -> float:
    """Recall@k = (# relevant in top k) / (total relevant that exist)."""
    if total_relevant <= 0:
        return 0.0
    top_k = relevance[:k]
    return sum(1 for r in top_k if r > 0) / total_relevant


def mean_reciprocal_rank(relevance: list[int]) -> float:
    """Mean Reciprocal Rank (MRR) — 1/rank of the first relevant result.

    Returns 0 if no relevant result exists in the list.
    Scale: (0, 1] where 1 means the first result is relevant.
    """
    for i, rel in enumerate(relevance, start=1):
        if rel > 0:
            return 1.0 / i
    return 0.0


def average_precision(relevance: list[int]) -> float:
    """Average Precision — precision computed at each relevant hit,
    then averaged. Rewards putting relevant results EARLY in the ranking.

    Binary: counts any relevance > 0 as relevant.
    """
    hits = 0
    sum_precisions = 0.0
    for i, rel in enumerate(relevance, start=1):
        if rel > 0:
            hits += 1
            sum_precisions += hits / i
    return sum_precisions / hits if hits > 0 else 0.0


def dcg_at_k(relevance: list[int], k: int) -> float:
    """Discounted Cumulative Gain@k — relevant results near the top
    count more than relevant results further down.

    Uses graded relevance (0-3).
    """
    total = 0.0
    for i, rel in enumerate(relevance[:k], start=1):
        total += (2**rel - 1) / math.log2(i + 1)
    return total


def ndcg_at_k(relevance: list[int], k: int) -> float:
    """Normalised DCG@k — DCG divided by the best-possible DCG (all
    relevant items ranked first). Scales to [0, 1].

    Uses graded relevance (0-3).
    """
    actual_dcg = dcg_at_k(relevance, k)
    ideal_relevance = sorted(relevance, reverse=True)
    ideal_dcg = dcg_at_k(ideal_relevance, k)
    return actual_dcg / ideal_dcg if ideal_dcg > 0 else 0.0


def evaluate_ranking(relevance: list[int], k: int = 10) -> dict:
    """Compute the full metric suite for one ranked result list.

    Args:
        relevance: List of relevance judgments (0-3), in rank order.
        k: Cutoff for @k metrics.

    Returns:
        Dict with all metrics.
    """
    total_relevant = sum(1 for r in relevance if r > 0)
    total_graded = sum(relevance)

    return {
        "precision_at_k": round(precision_at_k(relevance, k), 3),
        "graded_precision_at_k": round(graded_precision_at_k(relevance, k), 3),
        "average_precision": round(average_precision(relevance), 3),
        "mrr": round(mean_reciprocal_rank(relevance), 3),
        "ndcg_at_k": round(ndcg_at_k(relevance, k), 3),
        "num_relevant_found": total_relevant,
        "total_graded_score": total_graded,
        "num_judged": len(relevance),
    }
