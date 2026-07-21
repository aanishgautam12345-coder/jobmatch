"""Location Normalisation Processor.

Extracts structured location info from free text:
    (city, country, uk_country, uk_region, county, postcode_area, remote, workplace_type)

Handles:
    - "New York, NY, USA"
    - "London, United Kingdom"
    - "Remote"
    - "Hybrid - San Francisco"
    - "Manchester, England, UK"
    - "SW1A 1AA" (postcode area extraction)
    - Adzuna's pre-structured location strings
"""

import re
from typing import Optional


# ── Remote / Workplace Detection ──

REMOTE_KEYWORDS = [
    "remote", "work from home", "wfh", "distributed",
    "anywhere", "telecommute", "virtual", "fully remote",
]

HYBRID_KEYWORDS = ["hybrid", "flexible", "blended"]

ONSITE_KEYWORDS = ["on-site", "onsite", "in-office", "office-based"]


# ── Country Normalisations ──

COUNTRY_ALIASES: dict[str, str] = {
    "us": "United States", "usa": "United States", "united states of america": "United States",
    "united states": "United States",
    "uk": "United Kingdom", "gb": "United Kingdom", "great britain": "United Kingdom",
    "united kingdom": "United Kingdom",
    "de": "Germany", "deutschland": "Germany", "germany": "Germany",
    "fr": "France", "france": "France",
    "ca": "Canada", "canada": "Canada",
    "au": "Australia", "australia": "Australia",
    "in": "India", "india": "India",
    "nl": "Netherlands", "holland": "Netherlands", "netherlands": "Netherlands",
    "sg": "Singapore", "singapore": "Singapore",
    "jp": "Japan", "japan": "Japan",
    "nz": "New Zealand", "new zealand": "New Zealand",
    "ie": "Ireland", "ireland": "Ireland",
    "ch": "Switzerland", "switzerland": "Switzerland",
    "se": "Sweden", "sweden": "Sweden",
    "no": "Norway", "norway": "Norway",
    "dk": "Denmark", "denmark": "Denmark",
    "fi": "Finland", "finland": "Finland",
    "es": "Spain", "spain": "Spain",
    "it": "Italy", "italy": "Italy",
    "pt": "Portugal", "portugal": "Portugal",
    "br": "Brazil", "brazil": "Brazil",
    "mx": "Mexico", "mexico": "Mexico",
    "pl": "Poland", "poland": "Poland",
    "at": "Austria", "austria": "Austria",
    "be": "Belgium", "belgium": "Belgium",
    "np": "Nepal", "nepal": "Nepal",
}

# UK constituent countries
UK_COUNTRIES = {"england", "scotland", "wales", "northern ireland", "n. ireland"}


# ── UK Regions ──

UK_REGIONS: dict[str, str] = {
    # England
    "north east": "North East",
    "north west": "North West",
    "yorkshire and the humber": "Yorkshire and the Humber",
    "yorkshire": "Yorkshire and the Humber",
    "east midlands": "East Midlands",
    "west midlands": "West Midlands",
    "east of england": "East of England",
    "east": "East of England",
    "london": "London",
    "greater london": "London",
    "south east": "South East",
    "south west": "South West",
    # Scotland
    "central scotland": "Central Scotland",
    "west central scotland": "Central Scotland",
    "east scotland": "Eastern Scotland",
    "highlands and islands": "Highlands and Islands",
    "southern scotland": "Southern Scotland",
    # Wales
    "east wales": "East Wales",
    "west wales": "West Wales",
    "south wales": "West Wales",
    "north wales": "West Wales",
    # Northern Ireland
    "northern ireland": "Northern Ireland",
}


# ── UK Counties (major ones) ──

UK_COUNTIES: set[str] = {
    # England
    "bedfordshire", "berkshire", "bristol", "buckinghamshire", "cambridgeshire",
    "cheshire", "cornwall", "cumbria", "derbyshire", "devon", "dorset",
    "durham", "east sussex", "east riding of yorkshire", "essex", "gloucestershire",
    "greater london", "greater manchester", "hampshire", "herefordshire",
    "hertfordshire", "isle of wight", "kent", "lancashire", "leicestershire",
    "lincolnshire", "merseyside", "norfolk", "northamptonshire", "northumberland",
    "north yorkshire", "nottinghamshire", "oxfordshire", "rutland", "shropshire",
    "somerset", "south yorkshire", "staffordshire", "suffolk", "surrey",
    "tyne and wear", "warwickshire", "west midlands", "west sussex",
    "west yorkshire", "wiltshire", "worcestershire",
    # Scotland
    "aberdeenshire", "angus", "argyll and bute", "ayrshire", "banffshire",
    "berwickshire", "caithness", "clackmannanshire", "dumfriesshire",
    "dunbartonshire", "east lothian", "fife", "inverness-shire", "kincardineshire",
    "kinross-shire", "kirkcudbrightshire", "lanarkshire", "midlothian",
    "morayshire", "nairnshire", "orkney", "peeblesshire", "perthshire",
    "renfrewshire", "ross and cromarty", "roxburghshire", "selkirkshire",
    "shetland", "stirlingshire", "sutherland", "west lothian", "wigtownshire",
    # Wales
    "anglesey", "brecknockshire", "caernarfonshire", "cardiganshire",
    "carmarthenshire", "ceredigion", "denbighshire", "flintshire",
    "glamorgan", "merionethshire", "monmouthshire", "montgomeryshire",
    "pembrokeshire", "radnorshire",
    # Northern Ireland
    "antrim", "armagh", "down", "fermanagh", "londonderry", "tyrone",
}


# ── Postcode Area Patterns ──

# UK postcode areas: 1-2 letters + optional digits
POSTCODE_AREA_PATTERN = re.compile(
    r"\b([A-Z]{1,2})\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE
)

# Just the area prefix (e.g., "SW1", "EC1", "M1")
POSTCODE_PREFIX_PATTERN = re.compile(
    r"\b([A-Z]{1,2})\d", re.IGNORECASE
)

# All UK postcode area prefixes
POSTCODE_AREAS = {
    "AB", "AL", "B", "BA", "BB", "BD", "BH", "BL", "BN", "BR", "BT",
    "CA", "CB", "CF", "CH", "CM", "CO", "CR", "CT", "CV", "CW",
    "DA", "DD", "DE", "DG", "DH", "DL", "DN", "DT",
    "E", "EC", "EH", "EN", "EX",
    "FY", "FK",
    "G", "GL", "GU",
    "HA", "HD", "HG", "HP", "HR", "HS", "HU", "HX",
    "IG", "IP", "IV",
    "KA", "KT", "KW", "KY",
    "L", "LA", "LD", "LE", "LL", "LN", "LS", "LU",
    "M", "ME", "MK", "ML",
    "N", "NE", "NG", "NN", "NP", "NR", "NW",
    "OL", "OX",
    "PA", "PE", "PH", "PL", "PO", "PR",
    "RG", "RH", "RM",
    "S", "SA", "SE", "SG", "SK", "SL", "SM", "SN", "SO", "SP", "SR", "SS", "ST", "SW", "SY",
    "TA", "TD", "TF", "TN", "TQ", "TR", "TS", "TW",
    "UB",
    "W", "WA", "WC", "WD", "WF", "WN", "WR", "WS", "WV",
    "YO",
    "ZE",
}


# ── US States ──

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


def _extract_postcode_area(text: str) -> Optional[str]:
    """Extract UK postcode area prefix from text (e.g., 'SW1' from 'SW1A 1AA')."""
    if not text:
        return None
    match = POSTCODE_PREFIX_PATTERN.search(text)
    if match:
        area = match.group(1).upper()
        if area in POSTCODE_AREAS:
            return area
    return None


def _detect_uk_country(text: str) -> Optional[str]:
    """Detect UK constituent country from text."""
    text_lower = text.lower()
    if "northern ireland" in text_lower or "n. ireland" in text_lower:
        return "Northern Ireland"
    if "scotland" in text_lower or "scottish" in text_lower:
        return "Scotland"
    if "wales" in text_lower or "welsh" in text_lower:
        return "Wales"
    if "england" in text_lower or "english" in text_lower:
        return "England"
    return None


def _detect_uk_region(text: str) -> Optional[str]:
    """Detect UK region from text."""
    text_lower = text.lower()
    for keyword, region in UK_REGIONS.items():
        if keyword in text_lower:
            return region
    return None


def _detect_uk_county(text: str) -> Optional[str]:
    """Detect UK county from text."""
    text_lower = text.lower()
    for county in UK_COUNTIES:
        if county in text_lower:
            return county.title()
    return None


def _detect_workplace_type(
    location_text: str | None,
    description: str | None = None,
) -> Optional[str]:
    """Detect workplace type (remote/hybrid/onsite) from text."""
    all_text = f"{location_text or ''} {description or ''}".lower()

    if any(kw in all_text for kw in REMOTE_KEYWORDS):
        return "remote"
    if any(kw in all_text for kw in HYBRID_KEYWORDS):
        return "hybrid"
    if any(kw in all_text for kw in ONSITE_KEYWORDS):
        return "onsite"
    return None


def normalise_location(
    location_text: str | None,
    description: str | None = None,
) -> dict:
    """Normalise a location string into structured components.

    Args:
        location_text: Raw location string from the job posting.
        description: Full job description (fallback for remote detection).

    Returns:
        Dict with keys: city, country, uk_country, uk_region, county,
                        postcode_area, remote, workplace_type
    """
    result: dict = {
        "city": None,
        "country": None,
        "uk_country": None,
        "uk_region": None,
        "county": None,
        "postcode_area": None,
        "remote": False,
        "workplace_type": None,
    }

    # Check for remote in description as fallback
    all_text = f"{location_text or ''} {description or ''}".lower()

    # Detect remote
    if any(kw in all_text for kw in REMOTE_KEYWORDS):
        result["remote"] = True

    # Detect workplace type
    result["workplace_type"] = _detect_workplace_type(location_text, description)

    # Extract postcode area
    result["postcode_area"] = _extract_postcode_area(location_text or "")

    if not location_text or location_text.strip().lower() in ("remote", "anywhere", "worldwide"):
        result["remote"] = True
        return result

    # Clean the location string
    loc = location_text.strip()

    # Remove remote/hybrid prefixes
    loc = re.sub(r"(?i)^(remote|hybrid|on-?site)\s*[-–—:]\s*", "", loc)
    loc = re.sub(r"(?i)\s*\(?(remote|hybrid|on-?site)\)?$", "", loc)

    if not loc.strip():
        return result

    # Split by comma and clean parts
    parts = [p.strip() for p in loc.split(",") if p.strip()]

    if not parts:
        return result

    # Try to identify city and country from parts
    if len(parts) >= 2:
        last_part = parts[-1].strip().lower()

        # Check if last part is a US state abbreviation
        if parts[-1].strip().upper() in US_STATES:
            result["country"] = "United States"
        elif last_part in COUNTRY_ALIASES:
            result["country"] = COUNTRY_ALIASES[last_part]
        else:
            # Assume the last part is the country
            result["country"] = parts[-1].strip().title()

        # Only treat the first part as a city if it is NOT itself a
        # country code/name (avoids "UK, UK" -> city="UK", a false city)
        first_part_lower = parts[0].strip().lower()
        if first_part_lower not in COUNTRY_ALIASES and parts[0].strip().upper() not in US_STATES:
            result["city"] = parts[0]
    elif len(parts) == 1:
        part = parts[0].strip()
        part_lower = part.lower()

        # Check if it's a known country
        if part_lower in COUNTRY_ALIASES:
            result["country"] = COUNTRY_ALIASES[part_lower]
        else:
            # Assume it's a city
            result["city"] = part

    # ── UK-specific enrichment ──
    country_lower = (result["country"] or "").lower()
    full_text = f"{location_text or ''} {description or ''}"

    if country_lower in ("united kingdom", "uk", "gb"):
        result["uk_country"] = _detect_uk_country(full_text)
        result["uk_region"] = _detect_uk_region(full_text)
        result["county"] = _detect_uk_county(full_text)

        # If no UK country detected, default to England (most common)
        if not result["uk_country"]:
            result["uk_country"] = "England"

    return result
