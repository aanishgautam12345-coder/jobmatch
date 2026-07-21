"""Salary Standardisation Processor.

Parses salary information from various formats into a consistent structure.
Never fabricates a salary when missing. Stores original text and confidence.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedSalary:
    """Structured salary information extracted from text."""
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    currency: Optional[str] = None
    period: str = "annual"
    confidence: float = 0.0
    original_text: Optional[str] = None
    is_ote: bool = False
    is_doe: bool = False
    is_competitive: bool = False


CURRENCY_MAP: dict[str, str] = {
    "$": "USD", "usd": "USD", "us$": "USD",
    "£": "GBP", "gbp": "GBP",
    "€": "EUR", "eur": "EUR",
    "₹": "INR", "inr": "INR", "rs": "INR",
    "a$": "AUD", "aud": "AUD",
    "c$": "CAD", "cad": "CAD",
    "nz$": "NZD", "nzd": "NZD",
    "chf": "CHF", "sgd": "SGD", "s$": "SGD",
    "r": "ZAR", "zar": "ZAR",
    "rm": "MYR", "myr": "MYR",
    "pln": "PLN",
}

MULTIPLIERS: dict[str, float] = {
    "k": 1_000, "K": 1_000,
    "m": 1_000_000, "M": 1_000_000,
    "lpa": 100_000, "lakh": 100_000,
    "cr": 10_000_000,
}

ANNUAL_KEYWORDS = ["year", "annual", "annum", "yr", "p.a", "pa", "per annum", "yearly"]
MONTHLY_KEYWORDS = ["month", "mo", "monthly", "pm", "per month"]
WEEKLY_KEYWORDS = ["week", "wk", "weekly", "pw", "per week"]
HOURLY_KEYWORDS = ["hour", "hr", "hourly", "ph", "per hour"]
DAILY_KEYWORDS = ["day", "daily", "pd", "per day", "day rate", "contract rate"]

OTE_KEYWORDS = ["ote", "on target earnings", "on-target earnings"]
DOE_KEYWORDS = ["doe", "depends on experience", "dependent on experience"]
COMPETITIVE_KEYWORDS = ["competitive", "market rate", "market aligned"]

SALARY_PATTERN = re.compile(
    r"(?P<currency>[£$€₹]|(?:USD|GBP|EUR|INR|AUD|CAD|CHF|SGD|ZAR|MYR|PLN))\s*"
    r"(?P<min>[\d,]+(?:\.\d+)?)\s*(?P<min_mult>[kKmM])?"
    r"(?:\s*[-–—to]+\s*[£$€₹]?\s*(?P<max>[\d,]+(?:\.\d+)?)\s*(?P<max_mult>[kKmM])?)?",
    re.IGNORECASE,
)

BARE_SALARY_PATTERN = re.compile(
    r"(?:salary|pay|compensation|wage|rate)[:\s]*"
    r"(?P<min>[\d,]+(?:\.\d+)?)\s*(?P<min_mult>[kKmM])?"
    r"(?:\s*[-–—to]+\s*(?P<max>[\d,]+(?:\.\d+)?)\s*(?P<max_mult>[kKmM])?)?",
    re.IGNORECASE,
)

UP_TO_PATTERN = re.compile(
    r"(?:up\s+to|to|maximum|max)[:\s]*"
    r"[£$€₹]?\s*(?P<max>[\d,]+(?:\.\d+)?)\s*(?P<max_mult>[kKmM])?",
    re.IGNORECASE,
)

FROM_PATTERN = re.compile(
    r"(?:from|starting\s+at|minimum|min)[:\s]*"
    r"[£$€₹]?\s*(?P<min>[\d,]+(?:\.\d+)?)\s*(?P<min_mult>[kKmM])?",
    re.IGNORECASE,
)


def _detect_period(text: str) -> str:
    """Detect salary period from text context."""
    text_lower = text.lower()
    if any(kw in text_lower for kw in DAILY_KEYWORDS):
        return "daily"
    elif any(kw in text_lower for kw in HOURLY_KEYWORDS):
        return "hourly"
    elif any(kw in text_lower for kw in WEEKLY_KEYWORDS):
        return "weekly"
    elif any(kw in text_lower for kw in MONTHLY_KEYWORDS):
        return "monthly"
    return "annual"


def _parse_number(value: str, multiplier: Optional[str] = None) -> Optional[float]:
    """Parse a number string with optional multiplier."""
    try:
        num = float(value.replace(",", ""))
        if multiplier and multiplier in MULTIPLIERS:
            num *= MULTIPLIERS[multiplier]
        return num
    except (ValueError, TypeError):
        return None


def _calculate_confidence(
    has_currency: bool, has_range: bool, period_detected: bool,
    source_provided: bool, text_match_quality: bool,
) -> float:
    """Calculate extraction confidence (0.0-1.0)."""
    score = 0.0
    if source_provided:
        score += 0.4
    if has_currency:
        score += 0.2
    if has_range:
        score += 0.15
    if period_detected:
        score += 0.15
    if text_match_quality:
        score += 0.1
    return min(score, 1.0)


def _apply_sanity_bounds(result: ParsedSalary) -> ParsedSalary:
    """Reject salary values outside plausible real-world bounds."""
    bounds = {
        "annual": (1_000, 2_000_000),
        "monthly": (100, 150_000),
        "weekly": (25, 35_000),
        "daily": (5, 5_000),
        "hourly": (1, 1_000),
    }
    lo, hi = bounds.get(result.period, bounds["annual"])
    if result.min_salary is not None and not (lo <= result.min_salary <= hi):
        result.min_salary = None
        result.confidence *= 0.5
    if result.max_salary is not None and not (lo <= result.max_salary <= hi):
        result.max_salary = None
        result.confidence *= 0.5
    return result


def parse_salary(
    text: str | None,
    source_min: float | None = None,
    source_max: float | None = None,
    source_currency: str | None = None,
) -> ParsedSalary:
    """Parse salary from text or structured fields.

    Args:
        text: Free text that might contain salary info (description).
        source_min: Pre-structured min salary (e.g. from Adzuna API).
        source_max: Pre-structured max salary (e.g. from Adzuna API).
        source_currency: Currency code from source.

    Returns:
        ParsedSalary with standardised fields.
    """
    result = ParsedSalary(original_text=text)

    # Check for OTE/DOE/Competitive
    text_lower = (text or "").lower()
    if any(kw in text_lower for kw in OTE_KEYWORDS):
        result.is_ote = True
    if any(kw in text_lower for kw in DOE_KEYWORDS):
        result.is_doe = True
    if any(kw in text_lower for kw in COMPETITIVE_KEYWORDS):
        result.is_competitive = True

    # If we have structured data from the API, use it directly
    if source_min is not None or source_max is not None:
        result.min_salary = float(source_min) if source_min is not None else None
        result.max_salary = float(source_max) if source_max is not None else None
        result.period = "annual"
        result.currency = source_currency or None
        result.confidence = 0.9 if source_min or source_max else 0.0
        return _apply_sanity_bounds(result)

    if not text:
        return result

    text_lower = text.lower()

    # Check for "up to" / "from" patterns FIRST (before general pattern)
    up_match = UP_TO_PATTERN.search(text)
    from_match = FROM_PATTERN.search(text)

    if up_match and not from_match:
        result.max_salary = _parse_number(
            up_match.group("max"), up_match.group("max_mult")
        )
        result.period = _detect_period(text)
        result.confidence = 0.4
        # Parse currency from the match
        if up_match.group("max"):
            # Look for currency symbol near the number
            currency_match = re.search(r"[£$€₹]", text)
            if currency_match:
                result.currency = CURRENCY_MAP.get(currency_match.group().lower(), None)
        result = _apply_sanity_bounds(result)
        return result
    elif from_match and not up_match:
        result.min_salary = _parse_number(
            from_match.group("min"), from_match.group("min_mult")
        )
        result.period = _detect_period(text)
        result.confidence = 0.4
        currency_match = re.search(r"[£$€₹]", text)
        if currency_match:
            result.currency = CURRENCY_MAP.get(currency_match.group().lower(), None)
        result = _apply_sanity_bounds(result)
        return result

    # Try pattern with currency symbol first
    match = SALARY_PATTERN.search(text)
    has_currency = bool(match)

    if not match:
        match = BARE_SALARY_PATTERN.search(text)

    if not match:
        # No pattern matched at all
        return result

    groups = match.groupdict()

    # Parse currency
    currency_raw = groups.get("currency", "").strip()
    if currency_raw:
        result.currency = CURRENCY_MAP.get(currency_raw.lower(), currency_raw.upper())

    # Parse minimum
    min_val = groups.get("min")
    if min_val:
        result.min_salary = _parse_number(min_val, groups.get("min_mult"))

    # Parse maximum
    max_val = groups.get("max")
    if max_val:
        result.max_salary = _parse_number(max_val, groups.get("max_mult"))

    # If only one value found, it could be the max or a single figure
    if result.min_salary and not result.max_salary:
        result.max_salary = result.min_salary

    # Detect period
    result.period = _detect_period(text)

    # Calculate confidence
    has_range = result.min_salary is not None and result.max_salary is not None
    result.confidence = _calculate_confidence(
        has_currency=has_currency,
        has_range=has_range,
        period_detected=True,
        source_provided=False,
        text_match_quality=True,
    )

    result = _apply_sanity_bounds(result)
    return result
