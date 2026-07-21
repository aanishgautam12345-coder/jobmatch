"""Evaluation Harness — Semantic Search vs Keyword Search.

This is your dissertation's core evaluation methodology, executable:
    1. Runs a set of test queries against both search methods
    2. Lets you (the researcher) label each unique result with GRADED relevance
       — labels are SAVED, so you only judge each query/job pair once
    3. Computes Precision@k, MAP, MRR, and nDCG@k per method
    4. Exports a results table (CSV + Markdown) ready to paste into
       your dissertation's Results/Evaluation chapter

Relevance scale:
    0 = Not relevant
    1 = Partially relevant (tangentially related)
    2 = Relevant (genuinely useful match)
    3 = Highly relevant (strong, precise match)

Usage:
    python -m scripts.run_evaluation              # label + evaluate all test queries
    python -m scripts.run_evaluation --report-only # skip labeling, just report on existing labels
    python -m scripts.run_evaluation --binary      # use binary (0/1) labeling for faster judging
"""

import sys
import os
import json
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import *  # noqa: F401,F403
from app.services.search import semantic_search, keyword_search
from app.evaluation.metrics import evaluate_ranking


# ── Test query set ──
TEST_QUERIES = [
    "remote python developer",
    "senior data scientist machine learning",
    "HR generalist with payroll experience",
    "entry level marketing no experience",
    "backend engineer with cloud experience",
    "junior software developer",
    "customer support representative remote",
    "finance analyst with excel skills",
]

LABELS_FILE = Path(__file__).parent / "eval_labels.json"
RESULTS_LIMIT = 10


def load_labels() -> dict:
    if LABELS_FILE.exists():
        with open(LABELS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_labels(labels: dict):
    with open(LABELS_FILE, "w") as f:
        json.dump(labels, f, indent=2)


def label_key(query: str, job_id: str) -> str:
    return f"{query}::{job_id}"


def collect_labels(db, queries: list[str], binary: bool = False) -> dict:
    """Interactively label every unique result across both search methods
    for each query. Skips pairs already labeled in a previous run."""
    labels = load_labels()

    if binary:
        print("  Mode: BINARY (y = relevant, n = not relevant)")
    else:
        print("  Mode: GRADED (0 = not relevant, 1 = partial, 2 = relevant, 3 = highly relevant)")

    for query in queries:
        semantic_results = semantic_search(db, query=query, limit=RESULTS_LIMIT)
        keyword_results = keyword_search(db, query=query, limit=RESULTS_LIMIT)

        # Merge unique jobs across both result sets
        seen = {}
        for job in semantic_results + keyword_results:
            seen[job["id"]] = job

        unlabeled = [
            job for job in seen.values()
            if label_key(query, job["id"]) not in labels
        ]

        if not unlabeled:
            continue

        print(f"\n{'='*70}")
        print(f"  Query: \"{query}\"")
        print(f"  {len(unlabeled)} unlabeled result(s) to judge")
        print(f"{'='*70}")

        if binary:
            print("  Is this job a genuinely RELEVANT result for the query above?")
            print("  (y = relevant, n = not relevant, s = skip all remaining for this query)\n")
        else:
            print("  Rate this job's relevance to the query:")
            print("  (0 = not relevant, 1 = partially relevant, 2 = relevant, 3 = highly relevant, s = skip)")
            print("  Hint: 2 = 'I would apply to this', 3 = 'This is exactly what I'm looking for'\n")

        answer = None
        for job in unlabeled:
            print(f"  -> {job['title']}  |  {job.get('company') or 'N/A'}  |  {job.get('category', 'N/A')}")

            if binary:
                while True:
                    answer = input("    Relevant? [y/n/s]: ").strip().lower()
                    if answer in ("y", "n"):
                        labels[label_key(query, job["id"])] = 1 if answer == "y" else 0
                        save_labels(labels)
                        break
                    elif answer == "s":
                        break
                    else:
                        print("    Please enter y, n, or s")
            else:
                while True:
                    answer = input("    Relevance [0-3/s]: ").strip().lower()
                    if answer == "s":
                        break
                    try:
                        score = int(answer)
                        if 0 <= score <= 3:
                            labels[label_key(query, job["id"])] = score
                            save_labels(labels)
                            break
                        else:
                            print("    Please enter 0, 1, 2, 3, or s")
                    except ValueError:
                        print("    Please enter 0, 1, 2, 3, or s")

            if answer == "s":
                break

    return labels


def evaluate(db, queries: list[str], labels: dict) -> list[dict]:
    """Compute metrics for both methods across all queries."""
    rows = []

    for query in queries:
        semantic_results = semantic_search(db, query=query, limit=RESULTS_LIMIT)
        keyword_results = keyword_search(db, query=query, limit=RESULTS_LIMIT)

        semantic_relevance = [
            labels.get(label_key(query, job["id"]), 0) for job in semantic_results
        ]
        keyword_relevance = [
            labels.get(label_key(query, job["id"]), 0) for job in keyword_results
        ]

        semantic_metrics = evaluate_ranking(semantic_relevance, k=RESULTS_LIMIT)
        keyword_metrics = evaluate_ranking(keyword_relevance, k=RESULTS_LIMIT)

        rows.append({"query": query, "method": "Semantic (AI)", **semantic_metrics})
        rows.append({"query": query, "method": "Keyword (Baseline)", **keyword_metrics})

    return rows


def print_and_export(rows: list[dict]):
    """Print a summary table and export CSV + Markdown for the dissertation."""
    import csv

    # ── Console table ──
    print(f"\n\n{'='*110}")
    print("  EVALUATION RESULTS")
    print(f"{'='*110}")
    header = (f"{'Query':<35} {'Method':<20} {'P@10':<7} {'MAP':<7} "
              f"{'MRR':<7} {'nDCG@10':<9} {'Rel':<5}")
    print(header)
    print("-" * 110)
    for row in rows:
        print(f"{row['query']:<35} {row['method']:<20} {row['precision_at_k']:<7} "
              f"{row['average_precision']:<7} {row['mrr']:<7} "
              f"{row['ndcg_at_k']:<9} {row['num_relevant_found']:<5}")

    # ── Averages per method ──
    print(f"\n{'='*110}")
    print("  AVERAGES ACROSS ALL QUERIES")
    print(f"{'='*110}")
    for method in ["Semantic (AI)", "Keyword (Baseline)"]:
        method_rows = [r for r in rows if r["method"] == method]
        if not method_rows:
            continue
        avg_p = sum(r["precision_at_k"] for r in method_rows) / len(method_rows)
        avg_ap = sum(r["average_precision"] for r in method_rows) / len(method_rows)
        avg_mrr = sum(r["mrr"] for r in method_rows) / len(method_rows)
        avg_ndcg = sum(r["ndcg_at_k"] for r in method_rows) / len(method_rows)
        print(f"  {method:<20} P@10: {avg_p:.3f}  MAP: {avg_ap:.3f}  "
              f"MRR: {avg_mrr:.3f}  nDCG@10: {avg_ndcg:.3f}")

    # ── Export CSV ──
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / "evaluation_results.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    # ── Export Markdown ──
    md_path = output_dir / "evaluation_results.md"
    with open(md_path, "w") as f:
        f.write("# Evaluation Results: Semantic Search vs Keyword Search\n\n")
        f.write("| Query | Method | P@10 | MAP | MRR | nDCG@10 |\n")
        f.write("|---|---|---|---|---|---|\n")
        for row in rows:
            f.write(f"| {row['query']} | {row['method']} | {row['precision_at_k']} | "
                    f"{row['average_precision']} | {row['mrr']} | {row['ndcg_at_k']} |\n")

        f.write("\n## Averages\n\n")
        f.write("| Method | Mean P@10 | MAP | Mean MRR | Mean nDCG@10 |\n")
        f.write("|---|---|---|---|---|\n")
        for method in ["Semantic (AI)", "Keyword (Baseline)"]:
            method_rows = [r for r in rows if r["method"] == method]
            if not method_rows:
                continue
            avg_p = sum(r["precision_at_k"] for r in method_rows) / len(method_rows)
            avg_ap = sum(r["average_precision"] for r in method_rows) / len(method_rows)
            avg_mrr = sum(r["mrr"] for r in method_rows) / len(method_rows)
            avg_ndcg = sum(r["ndcg_at_k"] for r in method_rows) / len(method_rows)
            f.write(f"| {method} | {avg_p:.3f} | {avg_ap:.3f} | {avg_mrr:.3f} | {avg_ndcg:.3f} |\n")

    print(f"\n  Exported to:")
    print(f"    {csv_path}")
    print(f"    {md_path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate Semantic vs Keyword search")
    parser.add_argument("--report-only", action="store_true",
                        help="Skip labeling, just compute metrics on existing labels")
    parser.add_argument("--binary", action="store_true",
                        help="Use binary (0/1) labeling instead of graded (0-3)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("\n" + "="*70)
        print("  JobMatch AI - Evaluation Harness")
        print("="*70)
        print(f"  {len(TEST_QUERIES)} test queries")
        print(f"  Labels file: {LABELS_FILE}")

        if not args.report_only:
            labels = collect_labels(db, TEST_QUERIES, binary=args.binary)
        else:
            labels = load_labels()

        if not labels:
            print("\n  No labels found. Run without --report-only to label results first.")
            return

        rows = evaluate(db, TEST_QUERIES, labels)
        print_and_export(rows)

    finally:
        db.close()


if __name__ == "__main__":
    main()
