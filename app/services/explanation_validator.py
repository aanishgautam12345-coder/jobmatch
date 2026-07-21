"""RAG Explanation Validation — detects hallucinated claims in LLM output.

After the LLM generates an explanation, this module validates it against
the known facts (profile, job, breakdown) to catch:
- Hallucinated skills (skills mentioned but not in job or profile)
- Hallucinated salary figures (wrong numbers)
- Inconsistent claims (saying location fits when score is 0)

This addresses audit finding #14: RAG explanation has no validation.
"""

import re
import logging
from dataclasses import dataclass, field

from app.models.job import Job
from app.models.user import UserProfile
from app.services.recommendation import MatchBreakdown

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating an LLM explanation against known facts."""
    is_valid: bool = True
    confidence: float = 1.0  # 0.0-1.0 how confident we are in the validation
    issues: list[str] = field(default_factory=list)
    corrected_text: str | None = None  # If we can fix minor issues


def validate_explanation(
    explanation: str,
    profile: UserProfile,
    job: Job,
    breakdown: MatchBreakdown,
) -> ValidationResult:
    """Validate an LLM-generated explanation against known facts.

    Checks for:
    1. Hallucinated skills not in job or profile
    2. Salary figure accuracy
    3. Location claim consistency
    4. Score claim consistency

    Returns:
        ValidationResult with is_valid, issues list, and confidence.
    """
    result = ValidationResult()
    explanation_lower = explanation.lower()

    # ── Check 1: Hallucinated skills ──
    _check_skills(explanation_lower, profile, job, breakdown, result)

    # ── Check 2: Salary accuracy ──
    _check_salary(explanation_lower, job, result)

    # ── Check 3: Location consistency ──
    _check_location(explanation_lower, job, breakdown, result)

    # ── Check 4: Score consistency ──
    _check_scores(explanation_lower, breakdown, result)

    # If we found issues, reduce confidence
    if result.issues:
        result.confidence = max(0.3, 1.0 - len(result.issues) * 0.2)

    return result


def _check_skills(
    explanation_lower: str,
    profile: UserProfile,
    job: Job,
    breakdown: MatchBreakdown,
    result: ValidationResult,
):
    """Check for skills mentioned in explanation that aren't in job or profile."""
    # Extract potential skill mentions (capitalised words/phrases that look like skills)
    # Common skill patterns
    skill_patterns = [
        r"(?:proficiency in|experience with|skills? in|knowledge of|familiarity with)\s+([a-z][a-z\s,/+]+?)(?:\.|,|\s+and\s|\s+are\s|\s+is\s|$)",
        r"(?:uses?|using|requires?|requires? ([a-z][a-z\s,]+?))(?:\.|,|\s+and\s|$)",
    ]

    mentioned_skills = set()
    for pattern in skill_patterns:
        matches = re.findall(pattern, explanation_lower)
        for match in matches:
            # Split compound skill mentions
            for skill in re.split(r"[,/+]", match):
                skill = skill.strip().strip(".")
                if len(skill) > 2 and skill not in {
                    "the", "and", "for", "with", "this", "that", "your", "their",
                    "our", "its", "his", "her", "are", "is", "in", "at", "to",
                }:
                    mentioned_skills.add(skill)

    # Known skills from job and profile
    job_skills = {s.lower() for s in (breakdown.matching_skills + breakdown.missing_skills)}
    profile_skills = {s.lower() for s in (profile.skills or [])}
    known_skills = job_skills | profile_skills

    # Check each mentioned skill
    for skill in mentioned_skills:
        # Check if it's a substring of any known skill or vice versa
        found = False
        for known in known_skills:
            if skill in known or known in skill:
                found = True
                break
        if not found:
            result.issues.append(f"hallucinated_skill: '{skill}' not in job or profile")


def _check_salary(explanation_lower: str, job: Job, result: ValidationResult):
    """Check for salary figures in explanation that don't match the job."""
    # Extract salary mentions
    salary_pattern = r"(?:£|\$|€|gbp|usd|eur)\s*[\d,]+(?:k|K)?(?:\s*[-–—to]+\s*(?:£|\$|€)?\s*[\d,]+(?:k|K)?)?"
    mentioned = re.findall(salary_pattern, explanation_lower)

    if not mentioned:
        return

    # Get actual job salary
    actual_min = job.salary_min
    actual_max = job.salary_max

    if actual_min is None and actual_max is None:
        # Job has no salary — any salary claim is hallucinated
        result.issues.append(f"hallucinated_salary: explanation mentions salary '{mentioned[0]}' but job has no salary data")
        return

    # Extract numbers from mentioned salaries
    for mention in mentioned:
        numbers = re.findall(r"[\d,]+", mention.replace("k", "000").replace("K", "000"))
        for num_str in numbers:
            try:
                num = float(num_str.replace(",", ""))
                # Check if the number is wildly different from actual
                if actual_min and abs(num - actual_min) / max(actual_min, 1) > 0.5:
                    if actual_max and abs(num - actual_max) / max(actual_max, 1) > 0.5:
                        result.issues.append(
                            f"inaccurate_salary: '{mention}' doesn't match actual {actual_min}-{actual_max}"
                        )
            except ValueError:
                pass


def _check_location(explanation_lower: str, job: Job, breakdown: MatchBreakdown, result: ValidationResult):
    """Check for location claims inconsistent with the location fit score."""
    positive_location_claims = [
        "location fits", "location matches", "based in", "located in",
        "close to", "in your preferred", "near your",
    ]
    negative_location_claims = [
        "location doesn't match", "location is not", "different location",
        "far from",
    ]

    has_positive = any(claim in explanation_lower for claim in positive_location_claims)
    has_negative = any(claim in explanation_lower for claim in negative_location_claims)

    if has_positive and breakdown.location_fit < 0.3:
        result.issues.append(
            f"inconsistent_location_claim: says location fits but score is {breakdown.location_fit}"
        )

    if has_negative and breakdown.location_fit > 0.7:
        result.issues.append(
            f"inconsistent_location_claim: says location doesn't fit but score is {breakdown.location_fit}"
        )


def _check_scores(explanation_lower: str, breakdown: MatchBreakdown, result: ValidationResult):
    """Check for score claims that contradict the computed breakdown."""
    # Check "good match" claims against low scores
    good_match_phrases = ["strong match", "excellent match", "great match", "perfect match"]
    poor_match_phrases = ["poor match", "weak match", "low match", "not a good match"]

    has_good = any(phrase in explanation_lower for phrase in good_match_phrases)
    has_poor = any(phrase in explanation_lower for phrase in poor_match_phrases)

    if has_good and breakdown.overall_score < 0.3:
        result.issues.append(
            f"inconsistent_score_claim: calls it a strong match but score is {breakdown.match_percentage}%"
        )

    if has_poor and breakdown.overall_score > 0.7:
        result.issues.append(
            f"inconsistent_score_claim: calls it a poor match but score is {breakdown.match_percentage}%"
        )
