"""Canonical user preference values and validation helpers."""

JOB_TYPES = {
    "full-time": "Full-time",
    "part-time": "Part-time",
    "contract": "Contract",
    "temporary": "Temporary",
    "internship": "Internship",
}

NOTIFICATION_FREQUENCIES = {
    "instant": "Instant",
    "daily": "Daily",
    "weekly": "Weekly",
}

MIN_NOTIFICATION_SCORE = 0.0
MAX_NOTIFICATION_SCORE = 1.0


def validate_job_types(values: list[str]) -> list[str]:
    """Return unique canonical values, rejecting unknown input."""
    canonical = []
    for value in values:
        normalized = value.strip().lower()
        if normalized not in JOB_TYPES:
            raise ValueError(f"Unsupported job type: {value}")
        if normalized not in canonical:
            canonical.append(normalized)
    return canonical


def validate_notification_frequency(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in NOTIFICATION_FREQUENCIES:
        raise ValueError("Unsupported notification frequency")
    return normalized


def validate_notification_score(value: float) -> float:
    score = float(value)
    if not MIN_NOTIFICATION_SCORE <= score <= MAX_NOTIFICATION_SCORE:
        raise ValueError("Notification threshold must be between 0 and 1")
    return score
