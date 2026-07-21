"""RAG Explanation Engine.

Generates human-readable explanations for job recommendations, GROUNDED
in the actual computed score breakdown — not free generation. This is
what makes it "RAG" rather than plain prompting: the LLM only rephrases
facts it is given, it does not invent new claims about the match.

Pipeline:
    1. RETRIEVE  — pull the user profile facts + job facts + score breakdown
                    (already computed by the Recommendation Agent)
    2. AUGMENT   — build a prompt containing ONLY those retrieved facts
    3. GENERATE  — ask the LLM to explain the match using only that context
    4. VALIDATE  — check the generated explanation for hallucinated claims
"""

import hashlib
import logging

from openai import OpenAI

from app.config import get_settings
from app.models.job import Job
from app.models.user import UserProfile
from app.services.recommendation import MatchBreakdown
from app.services.explanation_validator import validate_explanation, ValidationResult

logger = logging.getLogger(__name__)


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Lazily initialise the OpenAI client."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set in .env. "
                "Get a key at https://platform.openai.com/api-keys"
            )
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _cache_key(profile: UserProfile, job: Job, breakdown: MatchBreakdown) -> str:
    """Generate a cache key from the profile, job, and breakdown."""
    key_parts = [
        str(profile.user_id),
        str(job.id),
        str(breakdown.match_percentage),
        str(breakdown.semantic_similarity),
        str(breakdown.skill_overlap),
    ]
    return hashlib.md5("|".join(key_parts).encode()).hexdigest()


# Simple in-memory cache for explanations (max 256 entries)
_explanation_cache: dict[str, str] = {}


def build_explanation_prompt(
    profile: UserProfile,
    job: Job,
    breakdown: MatchBreakdown,
) -> str:
    """Build a grounded prompt containing ONLY facts already computed.

    The LLM is not asked to judge the match — the match is already decided
    by the scoring engine. The LLM's only job is to explain it in plain
    English, using the retrieved evidence.
    """
    matching_skills = ", ".join(breakdown.matching_skills) if breakdown.matching_skills else "none identified"
    missing_skills = ", ".join(breakdown.missing_skills[:5]) if breakdown.missing_skills else "none"

    location_desc = "remote" if job.remote else (job.location_city or job.location_country or "unspecified location")
    salary_desc = (
        f"{job.salary_min or '?'}-{job.salary_max or '?'} {job.salary_currency or ''}"
        if (job.salary_min or job.salary_max) else "not disclosed"
    )
    user_min_salary = f"{profile.min_salary} {profile.salary_currency}" if profile.min_salary else "not specified"

    prompt = f"""You are explaining why a job was recommended to a candidate, using ONLY the facts below. Do not invent any information not stated here. Write 3 short sentences, plain English, no headers or bullet points.

CANDIDATE PROFILE:
- Headline: {profile.headline or "not specified"}
- Skills: {', '.join(profile.skills) if profile.skills else "not specified"}
- Experience level: {profile.experience_level or "not specified"} ({profile.experience_years or "?"} years)
- Preferred locations: {', '.join(profile.preferred_locations) if profile.preferred_locations else "not specified"}
- Minimum salary expectation: {user_min_salary}

JOB:
- Title: {job.title_clean or job.title}
- Company: {job.company or "not specified"}
- Location: {location_desc}
- Salary: {salary_desc}
- Category: {job.category or "not specified"}

COMPUTED MATCH EVIDENCE (already scored — do not re-judge, just explain):
- Overall match: {breakdown.match_percentage}%
- Semantic relevance to profile: {round(breakdown.semantic_similarity * 100, 1)}%
- Matching skills: {matching_skills}
- Skills the job wants that the candidate hasn't listed: {missing_skills}
- Location fit: {round(breakdown.location_fit * 100, 1)}%
- Salary fit: {round(breakdown.salary_fit * 100, 1)}%
- Experience level fit: {round(breakdown.experience_fit * 100, 1)}%

Write the explanation now, in 3 short sentences:"""

    return prompt


def generate_explanation(
    profile: UserProfile,
    job: Job,
    breakdown: MatchBreakdown,
    model: str = "",
    validate: bool = True,
) -> str:
    """Generate a grounded, human-readable explanation for a job match.

    Results are cached in memory to avoid repeated LLM calls for the same
    profile-job-breakdown combination.

    Args:
        profile: The user's profile.
        job: The recommended job.
        breakdown: The already-computed match score breakdown.
        model: OpenAI model to use (defaults to settings.openai_model).
        validate: If True, validate the explanation for hallucinated claims.

    Returns:
        A short, plain-English explanation string.
    """
    # Check cache first
    cache_key = _cache_key(profile, job, breakdown)
    if cache_key in _explanation_cache:
        return _explanation_cache[cache_key]

    prompt = build_explanation_prompt(profile, job, breakdown)
    settings = get_settings()
    model_name = model or settings.openai_model

    try:
        client = _get_client()
        response = client.responses.create(
            model=model_name,
            instructions="You explain job match results factually and concisely, using only the evidence given to you.",
            input=prompt,
            max_output_tokens=200,
        )
        raw = getattr(response, 'output_text', None)
        if not isinstance(raw, str) or not raw.strip():
            logger.warning("LLM returned empty or invalid output. Using fallback.")
            return _fallback_explanation(breakdown)

        explanation = raw.strip()

        # Validate the explanation for hallucinated claims
        if validate:
            validation = validate_explanation(explanation, profile, job, breakdown)
            if not validation.is_valid:
                logger.warning(
                    "Explanation validation failed (confidence=%s). Using fallback.",
                    validation.confidence,
                )
                return _fallback_explanation(breakdown)

        # Cache only non-empty explanations
        if explanation.strip() and len(_explanation_cache) < 256:
            _explanation_cache[cache_key] = explanation

        return explanation

    except Exception as e:
        logger.warning(f"OpenAI call failed ({type(e).__name__}). Using fallback.")
        return _fallback_explanation(breakdown)


def _fallback_explanation(breakdown: MatchBreakdown) -> str:
    """Template-based explanation used if the LLM call fails (e.g. no API key,
    rate limit, network issue). Keeps the feature working even offline."""
    parts = [f"This job scored {breakdown.match_percentage}% overall."]

    if breakdown.matching_skills:
        parts.append(f"It matches your skills in {', '.join(breakdown.matching_skills[:3])}.")

    if breakdown.location_fit >= 0.9:
        parts.append("The location fits your preferences well.")
    if breakdown.salary_fit >= 0.9:
        parts.append("The salary meets your expectations.")

    return " ".join(parts)