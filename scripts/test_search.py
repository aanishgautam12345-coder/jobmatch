"""Interactive Semantic Search Demo.

Run this to test your semantic search engine directly from the terminal —
no API or frontend needed yet. Great for a quick sanity check and demo.

Usage:
    python -m scripts.test_search
    python -m scripts.test_search "remote python developer"
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import *  # noqa: F401,F403
from app.services.search import semantic_search, keyword_search


def print_results(title: str, results: list[dict]):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

    if not results:
        print("  No results found.")
        return

    for i, job in enumerate(results, 1):
        match_info = f" | Match: {job['match_percentage']}%" if "match_percentage" in job else ""
        print(f"\n  {i}. {job['title']}{match_info}")
        print(f"     Company: {job.get('company') or 'N/A'}")
        loc = job.get("location_city") or job.get("location_country") or ("Remote" if job.get("remote") else "N/A")
        print(f"     Location: {loc}" + (" (Remote)" if job.get("remote") and job.get("location_city") else ""))
        if job.get("category"):
            print(f"     Category: {job['category']}")
        if job.get("salary_min") or job.get("salary_max"):
            print(f"     Salary: {job.get('salary_min', '?')} - {job.get('salary_max', '?')} {job.get('salary_currency', '')}")


def run_comparison(db, query: str):
    """Run both semantic and keyword search side by side — this IS your
    dissertation's core comparison."""
    print(f"\n\n🔍 Query: \"{query}\"")

    semantic_results = semantic_search(db, query, limit=5)
    print_results("🧠 SEMANTIC SEARCH (AI-powered, ranked by meaning)", semantic_results)

    keyword_results = keyword_search(db, query, limit=5)
    print_results("🔤 KEYWORD SEARCH (traditional baseline)", keyword_results)

    print(f"\n{'='*70}")
    print("  Compare: does semantic search surface relevant jobs that")
    print("  don't contain the exact keywords? That's your research finding.")
    print(f"{'='*70}\n")


def main():
    db = SessionLocal()
    try:
        if len(sys.argv) > 1:
            # Query provided as command line argument
            query = " ".join(sys.argv[1:])
            run_comparison(db, query)
        else:
            # Interactive mode
            print("\n" + "="*70)
            print("  JobMatch AI — Semantic Search Demo")
            print("="*70)
            print("  Type a search query (or 'quit' to exit)")
            print("  Examples: 'remote python developer', 'senior data scientist'")
            print("            'entry level marketing', 'HR manager with payroll experience'")
            print("="*70)

            while True:
                query = input("\n🔎 Search: ").strip()
                if query.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break
                if not query:
                    continue
                run_comparison(db, query)
    finally:
        db.close()


if __name__ == "__main__":
    main()
