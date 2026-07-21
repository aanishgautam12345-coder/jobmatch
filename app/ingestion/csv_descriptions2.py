"""CSV Ingestion Source — imports the job_descriptions2.csv dataset.

Expected CSV columns:
    Job Id, Experience, Qualifications, Salary Range, location, Country,
    latitude, longitude, Work Type, Company Size, Job Posting Date,
    Preference, Contact Person, Contact, Job Title, Role, Job Portal,
    Job Description, Benefits, skills, Responsibilities, Company, Company Profile

Usage:
    source = CsvDescriptions2Source("data/job_descriptions2.csv")
    records = source.fetch()
"""

import hashlib
import re
import pandas as pd
from pathlib import Path
from app.ingestion.base import JobSource, RawJobRecord


class CsvDescriptions2Source(JobSource):
    """Imports jobs from the job_descriptions2.csv dataset."""

    def __init__(self, file_path: str, limit: int | None = None):
        self.file_path = Path(file_path)
        self.limit = limit

    @property
    def source_name(self) -> str:
        return "csv2"

    def fetch(self) -> list[RawJobRecord]:
        if not self.file_path.exists():
            raise FileNotFoundError(f"CSV not found at {self.file_path}")

        print(f"Reading CSV: {self.file_path}")
        df = pd.read_csv(
            self.file_path,
            encoding="utf-8",
            on_bad_lines="skip",
            dtype=str,
        )

        if self.limit:
            df = df.head(self.limit)

        # Normalise column names (strip whitespace)
        df.columns = [c.strip() for c in df.columns]

        records = []
        skipped = 0
        for _, row in df.iterrows():
            title = _clean(row.get("Job Title"))
            description = _clean(row.get("Job Description"))

            # Skip rows with no title AND no description
            if not title and not description:
                skipped += 1
                continue

            # Stable dedup ID from title + first 200 chars of description
            raw_text = f"{title}-{(description or '')[:200]}"
            source_job_id = hashlib.md5(raw_text.encode()).hexdigest()

            # Parse salary range into structured min/max
            salary_min, salary_max = _parse_salary_range(
                _clean(row.get("Salary Range"))
            )

            # Combine location + country into one display string
            city = _clean(row.get("location"))
            country = _clean(row.get("Country"))
            location_display = ", ".join(
                part for part in [city, country] if part
            ) or None

            payload = {
                # Core fields — pipeline reads these keys
                "job_title": title,
                "job_description": description,
                "company": _clean(row.get("Company")),
                "category": _clean(row.get("Role")),
                "skills": _clean(row.get("skills")),
                # Location
                "location_display": location_display,
                # Salary (pre-parsed for the pipeline)
                "salary_min": salary_min,
                "salary_max": salary_max,
                # Job type
                "contract_type": _clean(row.get("Work Type")),
                # Experience
                "experience_level": _clean(row.get("Experience")),
                # Posted date
                "posted_at": _clean(row.get("Job Posting Date")),
                # Extra metadata (not used by pipeline but kept in payload)
                "qualifications": _clean(row.get("Qualifications")),
                "benefits": _clean(row.get("Benefits")),
                "responsibilities": _clean(row.get("Responsibilities")),
                "job_portal": _clean(row.get("Job Portal")),
                "company_size": _clean(row.get("Company Size")),
                "job_id": _clean(row.get("Job Id")),
                "country": country,
                "city": city,
            }

            records.append(
                RawJobRecord(
                    source="csv2",
                    source_job_id=source_job_id,
                    payload=payload,
                )
            )

        print(f"✓ Parsed {len(records)} jobs from CSV ({skipped} skipped — no title/description).")
        return records


def _clean(value) -> str | None:
    """Convert NaN / empty to None, strip whitespace."""
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value if value else None


def _parse_salary_range(salary_str: str | None) -> tuple[float | None, float | None]:
    """Parse salary range like '$59K-$99K' or '$120,000 - $150,000' into (min, max).

    Returns (min_salary, max_salary) as annual floats, or (None, None).
    """
    if not salary_str:
        return None, None

    # Match patterns like $59K-$99K, $59k - $99k, $120,000-$150,000
    match = re.search(
        r"\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?"
        r"\s*[-–—to]+\s*"
        r"\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?",
        salary_str,
    )
    if not match:
        return None, None

    min_val = _to_number(match.group(1), match.group(2))
    max_val = _to_number(match.group(3), match.group(4))

    return min_val, max_val


def _to_number(val: str | None, mult: str | None) -> float | None:
    if not val:
        return None
    try:
        num = float(val.replace(",", ""))
        if mult and mult.lower() == "k":
            num *= 1_000
        elif mult and mult.lower() == "m":
            num *= 1_000_000
        return num
    except (ValueError, TypeError):
        return None
