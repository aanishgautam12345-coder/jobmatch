"""Profile Completeness Service.

Calculates how complete a user profile is, providing:
- A 0-100 completeness score
- Per-field completeness breakdown
- Actionable guidance for the user to improve their profile

This directly addresses audit finding #20: users with empty profiles
get no recommendations but no guidance on how to improve.
"""

from dataclasses import dataclass, field
from app.models.user import UserProfile


@dataclass
class CompletenessResult:
    """Structured profile completeness assessment."""
    overall: float = 0.0        # 0-100
    filled_fields: int = 0
    total_fields: int = 0
    missing_fields: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# Fields and their weights (importance for recommendation quality)
FIELD_WEIGHTS = {
    "headline": 15,
    "skills": 25,
    "experience_level": 15,
    "preferred_locations": 15,
    "min_salary": 10,
    "preferred_job_types": 10,
    "career_interests": 5,
    "full_name": 3,
    "experience_years": 2,
}


def calculate_completeness(profile: UserProfile) -> CompletenessResult:
    """Calculate how complete a user profile is.

    Returns a CompletenessResult with overall score and breakdown.
    """
    result = CompletenessResult()
    result.total_fields = len(FIELD_WEIGHTS)

    score = 0.0
    missing = []
    recommendations = []

    # Check each field
    if profile.headline and str(profile.headline).strip():
        score += FIELD_WEIGHTS["headline"]
        result.filled_fields += 1
    else:
        missing.append("headline")
        recommendations.append("Add a professional headline (e.g. 'Senior Python Developer')")

    if profile.skills and len(profile.skills) > 0:
        score += FIELD_WEIGHTS["skills"]
        result.filled_fields += 1
    else:
        missing.append("skills")
        recommendations.append("List your key skills (e.g. 'Python, React, SQL')")

    if profile.experience_level and str(profile.experience_level).strip():
        score += FIELD_WEIGHTS["experience_level"]
        result.filled_fields += 1
    else:
        missing.append("experience_level")
        recommendations.append("Set your experience level (junior/mid/senior)")

    if profile.preferred_locations and len(profile.preferred_locations) > 0:
        score += FIELD_WEIGHTS["preferred_locations"]
        result.filled_fields += 1
    else:
        missing.append("preferred_locations")
        recommendations.append("Add preferred locations or mark as 'remote only'")

    if profile.min_salary is not None:
        score += FIELD_WEIGHTS["min_salary"]
        result.filled_fields += 1
    else:
        missing.append("min_salary")
        recommendations.append("Set a minimum salary expectation")

    if profile.preferred_job_types and len(profile.preferred_job_types) > 0:
        score += FIELD_WEIGHTS["preferred_job_types"]
        result.filled_fields += 1
    else:
        missing.append("preferred_job_types")
        recommendations.append("Select preferred job types (full-time/part-time/contract)")

    if profile.career_interests and str(profile.career_interests).strip():
        score += FIELD_WEIGHTS["career_interests"]
        result.filled_fields += 1
    else:
        missing.append("career_interests")
        recommendations.append("Describe your career interests")

    if profile.full_name and str(profile.full_name).strip():
        score += FIELD_WEIGHTS["full_name"]
        result.filled_fields += 1
    else:
        missing.append("full_name")

    if profile.experience_years is not None:
        score += FIELD_WEIGHTS["experience_years"]
        result.filled_fields += 1
    else:
        missing.append("experience_years")

    result.overall = round(min(score, 100.0), 1)
    result.missing_fields = missing
    result.recommendations = recommendations

    return result
