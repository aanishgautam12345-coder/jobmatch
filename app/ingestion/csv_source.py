"""CSV Ingestion Source — imports the Job Skill Set Kaggle dataset.

Expected CSV columns (from batuhanmutlu/job-skill-set):
    job_title, category, job_description, skills

Usage:
    source = CsvSource("data/job_skill_set.csv")
    records = source.fetch()
"""

import hashlib
import pandas as pd
from pathlib import Path
from app.ingestion.base import JobSource, RawJobRecord


class CsvSource(JobSource):
    """Imports jobs from the Kaggle Job Skill Set CSV."""

    def __init__(self, file_path: str, limit: int | None = None):
        self.file_path = Path(file_path)
        self.limit = limit  # Optional: cap rows for dev/testing

    @property
    def source_name(self) -> str:
        return "csv"

    def fetch(self) -> list[RawJobRecord]:
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"CSV not found at {self.file_path}. "
                f"Download from: kaggle.com/datasets/batuhanmutlu/job-skill-set"
            )

        print(f"Reading CSV: {self.file_path}")
        df = pd.read_csv(self.file_path, encoding="utf-8", on_bad_lines="skip")

        if self.limit:
            df = df.head(self.limit)

        records = []
        for idx, row in df.iterrows():
            # Build a stable ID from the row content so re-imports don't duplicate
            raw_text = f"{row.get('job_title', '')}-{row.get('job_description', '')[:200]}"
            source_job_id = hashlib.md5(raw_text.encode()).hexdigest()

            payload = {
                "job_title": _clean(row.get("job_title")),
                "category": _clean(row.get("category")),
                "job_description": _clean(row.get("job_description")),
                "skills": _clean(row.get("skills")),
            }

            records.append(
                RawJobRecord(
                    source="csv",
                    source_job_id=source_job_id,
                    payload=payload,
                )
            )

        print(f"✓ Parsed {len(records)} jobs from CSV.")
        return records


def _clean(value) -> str | None:
    """Convert NaN / empty to None, strip whitespace."""
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value if value else None
