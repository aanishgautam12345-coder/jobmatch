"""Job Quality Scoring Service.

Scores each processed job on completeness, freshness, description quality,
salary transparency, and metadata richness. Produces a 0-100 quality score
with breakdown for transparency and debugging.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class QualityScore:
    """Structured quality assessment for a job posting."""
    overall: float = 0.0          # 0-100 aggregate score
    completeness: float = 0.0     # How many fields are populated
    freshness: float = 0.0        # How recently posted
    description_quality: float = 0.0  # Length, structure, detail level
    salary_transparency: float = 0.0  # Whether salary is disclosed
    metadata_richness: float = 0.0    # Skills, company info, etc.
    flags: list[str] = field(default_factory=list)  # Quality flags for debugging


# Weights for the aggregate score
WEIGHTS = {
    "completeness": 0.30,
    "freshness": 0.20,
    "description_quality": 0.25,
    "salary_transparency": 0.15,
    "metadata_richness": 0.10,
}


def score_job(
    title: str | None = None,
    company: str | None = None,
    description: str | None = None,
    location_city: str | None = None,
    location_country: str | None = None,
    salary_min: float | None = None,
    salary_max: float | None = None,
    category: str | None = None,
    job_type: str | None = None,
    experience_level: str | None = None,
    skills: list[str] | None = None,
    posted_at: datetime | None = None,
    url: str | None = None,
    source: str | None = None,
) -> QualityScore:
    """Score a job posting on multiple quality dimensions.

    Returns a QualityScore with overall 0-100 score and breakdown.
    """
    result = QualityScore()

    # ── Completeness (0-100) ──
    fields = [title, company, description, location_city, location_country, category, job_type, url]
    filled = sum(1 for f in fields if f and str(f).strip())
    result.completeness = (filled / len(fields)) * 100

    if not title or not str(title).strip():
        result.flags.append("missing_title")
    if not company or not str(company).strip():
        result.flags.append("missing_company")
    if not description or not str(description).strip():
        result.flags.append("missing_description")

    # ── Freshness (0-100) ──
    if posted_at:
        age_days = (datetime.utcnow() - posted_at).days
        if age_days <= 1:
            result.freshness = 100.0
        elif age_days <= 7:
            result.freshness = 85.0
        elif age_days <= 14:
            result.freshness = 70.0
        elif age_days <= 30:
            result.freshness = 50.0
        elif age_days <= 60:
            result.freshness = 30.0
        elif age_days <= 90:
            result.freshness = 15.0
        else:
            result.freshness = 5.0
        result.flags.append(f"age_{age_days}d")
    else:
        result.freshness = 40.0  # Unknown age gets neutral score
        result.flags.append("no_post_date")

    # ── Description Quality (0-100) ──
    if description:
        desc_len = len(description)
        score = 0.0

        # Length scoring (ideal: 500-3000 chars)
        if desc_len < 50:
            score += 10
            result.flags.append("very_short_description")
        elif desc_len < 200:
            score += 30
            result.flags.append("short_description")
        elif desc_len < 500:
            score += 50
        elif desc_len < 3000:
            score += 80
        else:
            score += 70  # Very long descriptions may be raw HTML

        # Structure indicators
        lower_desc = description.lower()
        if any(kw in lower_desc for kw in ["responsibilities", "requirements", "about the role", "what you'll do"]):
            score += 15
        if any(kw in lower_desc for kw in ["benefits", "perks", "we offer", "what we offer"]):
            score += 5

        result.description_quality = min(score, 100.0)
    else:
        result.description_quality = 0.0
        result.flags.append("no_description")

    # ── Salary Transparency (0-100) ──
    if salary_min is not None and salary_max is not None:
        result.salary_transparency = 100.0
    elif salary_min is not None or salary_max is not None:
        result.salary_transparency = 60.0
        result.flags.append("partial_salary")
    else:
        result.salary_transparency = 0.0
        result.flags.append("no_salary")

    # ── Metadata Richness (0-100) ──
    meta_score = 0.0
    if skills and len(skills) > 0:
        meta_score += min(len(skills) * 5, 40)  # Up to 40 for skills
    if category and str(category).strip():
        meta_score += 15
    if job_type and str(job_type).strip():
        meta_score += 15
    if experience_level and str(experience_level).strip():
        meta_score += 10
    if url and str(url).strip():
        meta_score += 10
    if source and str(source).strip():
        meta_score += 5
    if location_city and str(location_city).strip():
        meta_score += 5

    result.metadata_richness = min(meta_score, 100.0)

    # ── Aggregate Score ──
    result.overall = (
        result.completeness * WEIGHTS["completeness"]
        + result.freshness * WEIGHTS["freshness"]
        + result.description_quality * WEIGHTS["description_quality"]
        + result.salary_transparency * WEIGHTS["salary_transparency"]
        + result.metadata_richness * WEIGHTS["metadata_richness"]
    )

    return result
