"""Run the Processing Pipeline.

Takes raw_jobs → cleans, normalises, extracts skills, generates embeddings → writes to jobs table.

Usage:
    python -m scripts.run_processing                    # process all
    python -m scripts.run_processing --limit 100        # process first 100
    python -m scripts.run_processing --no-embeddings    # skip embeddings (fast, for testing)
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.models import *  # noqa: F401,F403
from app.processing.pipeline import process_raw_jobs


def main():
    parser = argparse.ArgumentParser(description="Run the job processing pipeline")
    parser.add_argument("--limit", type=int, default=None, help="Max raw jobs to process")
    parser.add_argument("--no-embeddings", action="store_true",
                        help="Skip embedding generation (faster, for testing)")
    args = parser.parse_args()

    # Ensure tables exist
    init_db()

    db = SessionLocal()
    try:
        start = time.time()

        print("=" * 60)
        print("  JobMatch AI — Processing Pipeline")
        print("=" * 60)

        if args.no_embeddings:
            print("  ⚡ Embedding generation SKIPPED (--no-embeddings)")
        else:
            print("  🧠 Embedding generation ENABLED (first run downloads the model)")
            print("     This may take a few minutes on the first run ...")

        print()

        process_raw_jobs(
            db=db,
            limit=args.limit,
            generate_embeddings=not args.no_embeddings,
        )

        elapsed = time.time() - start
        print(f"\n  Completed in {elapsed:.1f} seconds.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
