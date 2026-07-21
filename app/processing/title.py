"""Title Cleaning Processor.

Cleans raw job titles by removing noise like:
- Seniority prefixes that vary across sources
- Req IDs, internal codes
- Gender markers (m/f/d)
- Extra whitespace and punctuation
"""

import re


# Patterns to strip from titles
NOISE_PATTERNS = [
    r"\(m/f/d\)",
    r"\(m/w/d\)",
    r"\(f/m/d\)",
    r"\(all genders\)",
    r"\(remote\)",
    r"\(hybrid\)",
    r"\(contract\)",
    r"\(freelance\)",
    r"req\s*#?\s*\d+",          # Req IDs like "Req #12345"
    r"job\s*id\s*:?\s*\d+",     # Job ID: 12345
    r"ref\s*:?\s*\w{5,}",       # Ref codes
    r"\s*-\s*\d{4,}$",          # Trailing numeric IDs
    r"\|.*$",                   # Everything after a pipe
    r"\*+",                     # Asterisks
]

COMPILED_NOISE = [re.compile(p, re.IGNORECASE) for p in NOISE_PATTERNS]


def clean_title(raw_title: str | None) -> str:
    """Clean a job title by removing noise patterns.

    Args:
        raw_title: The original job title.

    Returns:
        Cleaned title string.
    """
    if not raw_title:
        return ""

    title = raw_title.strip()

    # Remove noise patterns
    for pattern in COMPILED_NOISE:
        title = pattern.sub("", title)

    # Collapse multiple spaces
    title = re.sub(r"\s{2,}", " ", title).strip()

    # Remove trailing/leading dashes and colons
    title = title.strip("-:").strip()

    # Title case if ALL CAPS
    if title == title.upper() and len(title) > 3:
        title = title.title()

    return title
