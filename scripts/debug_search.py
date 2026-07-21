"""Debug Search — Diagnostic tool for investigating search results.

Usage:
    python scripts/debug_search.py --query "Azure" --limit 20
    python scripts/debug_search.py --query "Python" --limit 10
    python scripts/debug_search.py --query "Docker" --limit 5 --no-fallback

For each result, outputs:
    rank, job ID, title, company, query terms found, matched fields,
    lexical score, semantic score, profile score, final score,
    match type, currency, salary, duplicate group.
"""

import sys
import os
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.services.search import evidence_search, format_salary_display


def main():
    parser = argparse.ArgumentParser(description="Debug search results for a query")
    parser.add_argument("--query", "-q", required=True, help="Search query to debug")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Max results to show")
    parser.add_argument("--no-fallback", action="store_true", help="Disable semantic fallback")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        results = evidence_search(
            db,
            query=args.query,
            limit=args.limit,
            enable_semantic_fallback=not args.no_fallback,
        )
    finally:
        db.close()

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return

    print(f"\n{'='*100}")
    print(f"SEARCH DEBUG: query=\"{args.query}\" | results={len(results)}")
    print(f"{'='*100}\n")

    # Summary
    evidence_count = sum(1 for r in results if r.get("match_type") != "semantic_fallback")
    fallback_count = sum(1 for r in results if r.get("match_type") == "semantic_fallback")
    print(f"Evidence-backed results: {evidence_count}")
    print(f"Semantic fallback results: {fallback_count}")
    print()

    for rank, r in enumerate(results, 1):
        print(f"--- Result #{rank} ---")
        print(f"  Rank:            {rank}")
        print(f"  Job ID:          {r['id']}")
        print(f"  Title:           {r['title']}")
        print(f"  Company:         {r.get('company') or 'N/A'}")
        print(f"  Location:        {r.get('location_city') or r.get('location_country') or 'N/A'}")
        print(f"  Remote:          {r.get('remote', False)}")
        print(f"  Category:        {r.get('category') or 'N/A'}")
        print(f"  Source:          {r.get('source') or 'N/A'}")

        # Scores
        print(f"  ─── Scores ───")
        print(f"  Search relevance: {r.get('search_relevance_score', 0):.1f}/100")
        if r.get("profile_match_score") is not None:
            print(f"  Profile match:    {r['profile_match_score']:.1f}/100")
        print(f"  Ranking score:    {r.get('ranking_score', 0):.1f}/100")

        # Match evidence
        print(f"  ─── Match Evidence ───")
        print(f"  Match type:      {r.get('match_type', 'unknown')}")
        print(f"  Matched terms:   {r.get('matched_terms', [])}")
        print(f"  Matched fields:  {r.get('matched_fields', [])}")
        for ev in r.get("match_evidence", []):
            text = ev.get("text", "")[:80]
            print(f"    [{ev.get('field', '?')}] {text}")

        # Salary
        salary_disp = format_salary_display(
            r.get("salary_min"), r.get("salary_max"),
            r.get("salary_currency"), r.get("salary_period"),
        )
        print(f"  ─── Salary ───")
        print(f"  Display:         {salary_disp}")
        print(f"  Min:             {r.get('salary_min')}")
        print(f"  Max:             {r.get('salary_max')}")
        print(f"  Currency:        {r.get('salary_currency')}")
        print(f"  Period:          {r.get('salary_period')}")

        # Dedup
        if r.get("duplicate_group") is not None:
            print(f"  Duplicate group: {r['duplicate_group']}")

        print()


if __name__ == "__main__":
    main()
