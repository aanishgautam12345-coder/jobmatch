"""Duplicate Detection Processor.

Two-stage deduplication with audit trail:
1. Exact: SHA-256 hash of normalised (title + company + location)
2. Near-duplicate: multi-signal fuzzy matching (title, company, location, salary, description)

Stage 1 runs at insert time (dedup_hash unique constraint).
Stage 2 can run as a batch cleanup.

Each dedup decision produces an audit record for traceability.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz


@dataclass
class DedupAuditRecord:
    """Audit trail for a dedup decision."""
    title_similarity: float = 0.0
    company_similarity: float = 0.0
    location_similarity: float = 0.0
    salary_overlap: float = 0.0
    description_similarity: float = 0.0
    combined_score: float = 0.0
    is_duplicate: bool = False
    method: str = "exact"  # exact/fuzzy/combined


def generate_dedup_hash(
    title: str,
    company: str | None,
    location: str | None,
    salary_min: float | None = None,
    salary_max: float | None = None,
) -> str:
    """Generate a deterministic hash for exact duplicate detection.

    Includes salary range to avoid conflating different seniority levels.
    """
    parts = [
        (title or "").lower().strip(),
        (company or "").lower().strip(),
        (location or "").lower().strip(),
        str(int(salary_min or 0)),
        str(int(salary_max or 0)),
    ]
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def is_near_duplicate(
    title_a: str,
    company_a: str | None,
    title_b: str,
    company_b: str | None,
    location_a: str | None = None,
    location_b: str | None = None,
    salary_min_a: float | None = None,
    salary_max_a: float | None = None,
    salary_min_b: float | None = None,
    salary_max_b: float | None = None,
    description_a: str | None = None,
    description_b: str | None = None,
    threshold: float = 0.85,
    audit: bool = False,
) -> bool | tuple[bool, DedupAuditRecord]:
    """Check if two jobs are near-duplicates using multi-signal fuzzy matching.

    Args:
        title_a, title_b: Job titles.
        company_a, company_b: Company names.
        location_a, location_b: Location strings.
        salary_min_a, salary_max_a: Salary range for job A.
        salary_min_b, salary_max_b: Salary range for job B.
        description_a, description_b: Full descriptions.
        threshold: Combined score threshold (0.0-1.0) to consider duplicate.
        audit: If True, return audit record alongside result.

    Returns:
        bool if audit=False, (bool, DedupAuditRecord) if audit=True.
    """
    record = DedupAuditRecord()

    # Title similarity (token set ratio handles word order differences)
    record.title_similarity = fuzz.token_set_ratio(
        (title_a or "").lower(), (title_b or "").lower()
    ) / 100.0

    # Company similarity
    record.company_similarity = fuzz.token_set_ratio(
        (company_a or "").lower(), (company_b or "").lower()
    ) / 100.0

    # Location similarity
    record.location_similarity = fuzz.token_set_ratio(
        (location_a or "").lower(), (location_b or "").lower()
    ) / 100.0

    # Salary overlap
    record.salary_overlap = _salary_overlap(
        salary_min_a, salary_max_a, salary_min_b, salary_max_b
    )

    # Description similarity (only if both provided, using partial_ratio for speed)
    if description_a and description_b:
        record.description_similarity = fuzz.partial_ratio(
            description_a[:2000], description_b[:2000]
        ) / 100.0
    else:
        record.description_similarity = 0.0

    # Combined score: title and company are strongest signals
    record.combined_score = (
        record.title_similarity * 0.35
        + record.company_similarity * 0.25
        + record.location_similarity * 0.15
        + record.salary_overlap * 0.15
        + record.description_similarity * 0.10
    )

    record.is_duplicate = record.combined_score >= threshold
    record.method = "combined"

    if audit:
        return record.is_duplicate, record
    return record.is_duplicate


def _salary_overlap(
    min_a: float | None,
    max_a: float | None,
    min_b: float | None,
    max_b: float | None,
) -> float:
    """Calculate salary range overlap as a score (0.0-1.0).

    Returns 1.0 for identical ranges, 0.0 for no overlap.
    """
    if not all([min_a, max_a, min_b, max_b]):
        return 0.0

    a_lo, a_hi = float(min_a), float(max_a)
    b_lo, b_hi = float(min_b), float(max_b)

    # Calculate overlap
    overlap_lo = max(a_lo, b_lo)
    overlap_hi = min(a_hi, b_hi)

    if overlap_lo >= overlap_hi:
        return 0.0  # No overlap

    overlap = overlap_hi - overlap_lo
    range_a = a_hi - a_lo if a_hi > a_lo else 1.0
    range_b = b_hi - b_lo if b_hi > b_lo else 1.0
    min_range = min(range_a, range_b)

    if min_range <= 0:
        return 0.0

    return min(overlap / min_range, 1.0)
