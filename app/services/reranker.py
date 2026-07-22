"""Cross-Encoder Reranker Service.

Re-ranks an initial candidate list using a cross-encoder model.
Cross-encoder models take (query, document) pairs and produce a relevance
score, which is more accurate than bi-encoder cosine similarity alone.

Uses a lightweight model suitable for CPU inference to stay zero-cost.
Falls back gracefully if the model is unavailable.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# Model config — kept lightweight for CPU inference
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
MAX_SEQUENCE_LENGTH = 512


@dataclass
class RerankResult:
    """A single reranked result."""
    index: int        # Original position in the candidate list
    score: float      # Cross-encoder relevance score
    original_score: float  # Pre-reranking score for comparison


@lru_cache(maxsize=1)
def _get_reranker():
    """Load the cross-encoder model once and cache it."""
    try:
        from sentence_transformers import CrossEncoder
        logger.info(f"Loading reranker model: {RERANKER_MODEL}")
        model = CrossEncoder(RERANKER_MODEL, max_length=MAX_SEQUENCE_LENGTH)
        logger.info("Reranker model loaded.")
        return model
    except Exception as e:
        logger.warning(f"Failed to load reranker model: {e}. Reranking disabled.")
        return None


def rerank_candidates(
    query: str,
    candidates: list[dict],
    top_n: int | None = None,
    score_field: str = "title",
) -> list[dict]:
    """Re-rank candidate jobs using a cross-encoder model.

    Args:
        query: The search query (user profile text or search terms).
        candidates: List of candidate dicts, each must have at least `title`.
        top_n: If provided, return only the top_n results after reranking.
        score_field: Field to use as the document text for reranking.
            Defaults to "title". Can also be "title_clean" or a custom key.

    Returns:
        The same candidate list, reordered by cross-encoder relevance score.
        Each dict gets an added "rerank_score" field.
    """
    model = _get_reranker()

    if model is None or not candidates:
        # Fallback: return original order unchanged
        return candidates

    # Build (query, document) pairs for the cross-encoder
    pairs = []
    for c in candidates:
        doc_text = c.get(score_field) or c.get("title") or ""
        # Include company and location for richer matching
        company = c.get("company", "")
        location = c.get("location_city") or c.get("location_country") or ""
        parts = [doc_text, company, location]
        # Include skills if available
        skills = c.get("skills")
        if skills:
            if isinstance(skills, list):
                skills = ", ".join(skills)
            parts.append(f"Skills: {skills}")
        # Include a summary of the description if available
        description = c.get("description")
        if description:
            # Take first 300 chars of description for context
            parts.append(description[:300])
        doc_text = " | ".join(p for p in parts if p).strip()
        pairs.append((query, doc_text[:MAX_SEQUENCE_LENGTH]))

    # Score all pairs
    try:
        scores = model.predict(pairs, show_progress_bar=False)
    except Exception as e:
        logger.warning(f"Reranking failed: {e}. Returning original order.")
        return candidates

    # Attach scores and sort
    for i, (candidate, score) in enumerate(zip(candidates, scores)):
        candidate["rerank_score"] = float(score)
        candidate["rerank_original_index"] = i

    reranked = sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)

    if top_n is not None:
        reranked = reranked[:top_n]

    return reranked


def is_reranker_available() -> bool:
    """Check if the reranker model is loaded and available."""
    return _get_reranker() is not None
