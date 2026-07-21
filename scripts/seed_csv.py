"""Seed the database from a CSV dataset.

Usage:
    # Original Job Skill Set (13k rows, basic fields)
    python -m scripts.seed_csv --source csv
    python -m scripts.seed_csv --source csv --limit 500

    # job_descriptions2.csv (1M+ rows, rich fields)
    python -m scripts.seed_csv --source csv2
    python -m scripts.seed_csv --source csv2 --limit 500

Processing (raw_jobs → jobs) runs separately via run_processing.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.dialects.postgresql import insert
from app.database import SessionLocal, init_db
from app.models import *  # noqa: F401,F403
from app.models.job import RawJob

SOURCES = {
    "csv": {
        "file": "data/job_skill_set.csv",
        "class": "app.ingestion.csv_source:CsvSource",
    },
    "csv2": {
        "file": "data/job_descriptions2.csv",
        "class": "app.ingestion.csv_descriptions2:CsvDescriptions2Source",
    },
}


def _get_source(source_name: str, file_path: str, limit: int | None):
    if source_name == "csv":
        from app.ingestion.csv_source import CsvSource
        return CsvSource(file_path, limit=limit)
    elif source_name == "csv2":
        from app.ingestion.csv_descriptions2 import CsvDescriptions2Source
        return CsvDescriptions2Source(file_path, limit=limit)
    else:
        raise ValueError(f"Unknown source: {source_name}. Choose from: {list(SOURCES.keys())}")


def seed(source_name: str, file_path: str | None = None, limit: int | None = None):
    # Ensure tables exist
    init_db()

    # Resolve file path
    if not file_path:
        file_path = SOURCES[source_name]["file"]

    # Fetch records from CSV
    source = _get_source(source_name, file_path, limit)
    records = source.fetch()

    # Write to raw_jobs, skip duplicates
    db = SessionLocal()
    inserted = 0
    skipped = 0

    try:
        for record in records:
            stmt = insert(RawJob).values(
                source=record.source,
                source_job_id=record.source_job_id,
                payload=record.payload,
                processed=False,
            ).on_conflict_do_nothing(
                index_elements=["source", "source_job_id"]
            )
            result = db.execute(stmt)
            if result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        db.commit()
        print(f"\n✓ Seed complete: {inserted} inserted, {skipped} skipped (duplicates).")
        print(f"  Total raw_jobs in DB: {db.query(RawJob).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed raw_jobs from CSV")
    parser.add_argument(
        "--source", choices=["csv", "csv2"], default="csv",
        help="CSV source: csv (job_skill_set) or csv2 (job_descriptions2)"
    )
    parser.add_argument("--file", default=None, help="Override CSV file path")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to import")
    args = parser.parse_args()

    seed(args.source, args.file, args.limit)
