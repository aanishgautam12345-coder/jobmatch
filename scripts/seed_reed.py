"""Seed the database from the Reed.co.uk API.

Usage:
    python -m scripts.seed_reed --keywords "python developer" --location "london"
    python -m scripts.seed_reed --keywords "data scientist" --fullTime --limit 50
    python -m scripts.seed_reed --keywords "software engineer" --distance 25 --maxPages 3

Processing (raw_jobs -> jobs) runs separately via run_processing.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.dialects.postgresql import insert
from app.database import SessionLocal, init_db
from app.models import *  # noqa: F401,F403
from app.models.job import RawJob
from app.ingestion.reed_source import ReedSource


def seed(
    keywords: str = "",
    location: str = "",
    distance: int = 10,
    full_time: bool | None = None,
    part_time: bool | None = None,
    permanent: bool | None = None,
    contract: bool | None = None,
    temp: bool | None = None,
    min_salary: int | None = None,
    max_salary: int | None = None,
    limit: int | None = None,
    max_pages: int = 5,
):
    # Ensure tables exist
    init_db()

    # Calculate how many pages we need
    results_per_page = 100
    if limit:
        max_pages = max(1, (limit + results_per_page - 1) // results_per_page)

    # Fetch records from Reed API
    source = ReedSource(
        keywords=keywords,
        location=location,
        distance=distance,
        full_time=full_time,
        part_time=part_time,
        permanent=permanent,
        contract=contract,
        temp=temp,
        min_salary=min_salary,
        max_salary=max_salary,
        results_to_take=results_per_page,
        max_pages=max_pages,
    )
    records = source.fetch()

    # Apply limit if specified
    if limit:
        records = records[:limit]

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
        print(f"\nSeed complete: {inserted} inserted, {skipped} skipped (duplicates).")
        print(f"  Total raw_jobs in DB: {db.query(RawJob).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed raw_jobs from Reed.co.uk API")
    parser.add_argument("--keywords", default="", help="Search keywords")
    parser.add_argument("--location", default="", help="Location name")
    parser.add_argument("--distance", type=int, default=10, help="Distance from location in miles")
    parser.add_argument("--fullTime", action="store_true", help="Filter full-time jobs")
    parser.add_argument("--partTime", action="store_true", help="Filter part-time jobs")
    parser.add_argument("--permanent", action="store_true", help="Filter permanent jobs")
    parser.add_argument("--contract", action="store_true", help="Filter contract jobs")
    parser.add_argument("--temp", action="store_true", help="Filter temporary jobs")
    parser.add_argument("--minSalary", type=int, default=None, help="Minimum salary")
    parser.add_argument("--maxSalary", type=int, default=None, help="Maximum salary")
    parser.add_argument("--limit", type=int, default=None, help="Max jobs to import")
    parser.add_argument("--maxPages", type=int, default=5, help="Max pages to fetch (100 results/page)")
    args = parser.parse_args()

    seed(
        keywords=args.keywords,
        location=args.location,
        distance=args.distance,
        full_time=args.fullTime if args.fullTime else None,
        part_time=args.partTime if args.partTime else None,
        permanent=args.permanent if args.permanent else None,
        contract=args.contract if args.contract else None,
        temp=args.temp if args.temp else None,
        min_salary=args.minSalary,
        max_salary=args.maxSalary,
        limit=args.limit,
        max_pages=args.maxPages,
    )
