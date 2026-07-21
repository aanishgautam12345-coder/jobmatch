# Evaluation Baseline

**Date:** 2026-07-13
**Scope:** Current evaluation capabilities, metrics, and gaps

---

## 1. Current Evaluation Infrastructure

### 1.1 Metrics Implemented
**File:** `app/evaluation/metrics.py` (88 lines)

| Metric | Function | Status |
|--------|----------|--------|
| Precision@k | `precision_at_k(relevance, k)` | Implemented |
| Recall@k | `recall_at_k(relevance, k, total_relevant)` | Implemented |
| Average Precision | `average_precision(relevance)` | Implemented |
| DCG@k | `dcg_at_k(relevance, k)` | Implemented |
| nDCG@k | `ndcg_at_k(relevance, k)` | Implemented |
| Full suite | `evaluate_ranking(relevance, k)` | Implemented |

### 1.2 Evaluation Harness
**File:** `scripts/run_evaluation.py` (232 lines)

| Feature | Status |
|---------|--------|
| Test query set (8 queries) | Defined |
| Interactive labeling (y/n/s) | Implemented |
| Label persistence (JSON) | Implemented |
| Semantic vs keyword comparison | Implemented |
| CSV export | Implemented |
| Markdown export | Implemented |
| Per-query metrics | Implemented |
| Average metrics | Implemented |

### 1.3 Test Queries
```python
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
```

---

## 2. What Works

1. **Metric functions are correct.** Precision@k, MAP, nDCG@k implementations follow standard formulas.
2. **Label persistence works.** Labels saved after each judgment; re-runnable without losing progress.
3. **Comparison framework exists.** Can compare semantic vs keyword side-by-side.
4. **Export formats ready.** CSV and Markdown output can be pasted into dissertation.

---

## 3. Critical Gaps

| # | Gap | Impact | Phase |
|---|-----|--------|-------|
| 1 | **Binary relevance only (0/1).** Cannot distinguish strong from weak matches. | Cannot demonstrate nuanced ranking quality. | Phase 7 |
| 2 | **No MRR (Mean Reciprocal Rank).** Missing standard metric. | Incomplete metric suite. | Phase 7 |
| 3 | **No Recall@k in harness.** Function exists but harness doesn't compute it. Missing `total_relevant` count. | Cannot measure recall. | Phase 7 |
| 4 | **No ablation studies.** Cannot remove components and measure impact. | Cannot demonstrate contribution of individual features. | Phase 7 |
| 5 | **No statistical analysis.** No confidence intervals, no significance tests. | Cannot claim results are statistically meaningful. | Phase 7 |
| 6 | **No explanation evaluation.** No hallucination rate, grounding checks, or faithfulness metrics. | Cannot validate RAG quality. | Phase 7 |
| 7 | **No latency measurement.** Search and recommendation timing not captured. | Cannot demonstrate efficiency. | Phase 7 |
| 8 | **No diversity metrics.** Cannot measure category or employer diversity. | Missing important quality indicator. | Phase 7 |
| 9 | **No reproducible evaluation corpus.** Test queries are hardcoded; no fixed vacancy corpus for reproducibility. | Results not reproducible. | Phase 7 |
| 10 | **No graded relevance labels.** Existing labels are binary. | Cannot compute gain-based metrics properly. | Phase 7 |
| 11 | **No inter-rater agreement.** Single-assessor labels only. | Cannot demonstrate annotation quality. | Phase 7 |
| 12 | **No cross-encoder comparison.** No reranker to evaluate. | Missing key comparison. | Phase 3 |

---

## 4. Search Methods Currently Available for Comparison

| Method | Function | Description |
|--------|----------|-------------|
| Semantic Search | `semantic_search()` | pgvector cosine distance, no filters |
| Keyword Search | `keyword_search()` | ILIKE AND-match, no ranking |
| Hybrid Search | `hybrid_search()` | Semantic + SQL filters |
| Similar Jobs | `find_similar_jobs()` | Vector similarity to reference job |

### What's Missing for Full Comparison

| Method | Status | Phase |
|--------|--------|-------|
| PostgreSQL full-text search (tsvector) | Not implemented | Phase 3 |
| Hybrid with rank fusion | Not implemented | Phase 3 |
| Cross-encoder reranked | Not implemented | Phase 3 |
| Personalised recommendation | Implemented but not in evaluation harness | Phase 4 |

---

## 5. Recommendation Evaluation

### Current State
- Recommendation agent produces ranked lists with score breakdowns.
- No evaluation against ground truth for recommendations.
- No user interaction data to measure implicit relevance.

### What's Needed

| Feature | Status | Phase |
|---------|--------|-------|
| Profile-job relevance labels | Missing | Phase 7 |
| Recommendation hit rate | Missing | Phase 7 |
| Click-through rate | Missing (no tracking) | Phase 4 |
| Save rate | Missing (no tracking) | Phase 4 |
| Application rate | Missing (no tracking) | Phase 4 |

---

## 6. Explanation Evaluation

### Current State
- RAG explanations generated via Groq LLM.
- Fallback template exists.
- No validation of generated explanations.

### What's Needed

| Feature | Status | Phase |
|---------|--------|-------|
| Factual correctness checking | Missing | Phase 5 |
| Groundedness verification | Missing | Phase 5 |
| Hallucination rate measurement | Missing | Phase 7 |
| Evidence coverage scoring | Missing | Phase 7 |
| User trust assessment | Missing | Phase 7 |

---

## 7. Evaluation Configuration

### Current Settings
```python
RESULTS_LIMIT = 10  # k for @k metrics
LABELS_FILE = Path(__file__).parent / "eval_labels.json"
```

### Existing Evaluation Results
**File:** `data/evaluation_results.csv` and `data/evaluation_results.md`

These contain pre-computed results from a previous evaluation run, but the methodology is not documented.

---

## 8. Dissertation Alignment

### What the Current System Can Demonstrate
1. Semantic search vs keyword search (binary relevance)
2. Precision@k and nDCG@k comparison
3. Qualitative examples of semantic vs keyword results

### What the Dissertation Needs but Is Missing
1. Graded relevance evaluation (0-3 scale)
2. Statistical significance testing
3. Ablation studies (remove lexical, vector, reranker, individual scores)
4. Cross-encoder reranking comparison
5. Hybrid retrieval (lexical + semantic + fusion) comparison
6. Explanation faithfulness evaluation
7. Latency and efficiency measurements
8. Reproducible evaluation corpus with annotation guidelines
9. Inter-rater agreement (if multiple assessors)
10. Comprehensive results tables with confidence intervals

---

## 9. Recommended Evaluation Architecture

```
evaluation/
├── corpus/
│   ├── jobs/              # Fixed UK vacancy corpus
│   ├── profiles/          # Synthetic/consenting user profiles
│   ├── relevance_labels/  # Graded relevance (0-3)
│   └── annotation_guide.md
├── systems/
│   ├── keyword_search.py
│   ├── semantic_search.py
│   ├── full_text_search.py
│   ├── hybrid_search.py
│   ├── hybrid_reranked.py
│   └── personalised_recommendations.py
├── metrics/
│   ├── precision_recall.py
│   ├── ranking.py (nDCG, MRR, MAP)
│   ├── diversity.py
│   ├── latency.py
│   └── explanation.py
├── runners/
│   ├── benchmark_runner.py
│   ├── ablation_runner.py
│   └── explanation_evaluator.py
├── analysis/
│   ├── statistical_tests.py
│   └── visualization.py
└── results/
    ├── raw/
    └── formatted/
```

---

## 10. Summary

| Aspect | Status | Readiness |
|--------|--------|-----------|
| Basic metrics | Implemented | Ready |
| Evaluation harness | Implemented | Needs enhancement |
| Graded relevance | Missing | Phase 7 |
| Statistical analysis | Missing | Phase 7 |
| Ablation studies | Missing | Phase 7 |
| Explanation evaluation | Missing | Phase 7 |
| Reproducible corpus | Missing | Phase 7 |
| Cross-encoder comparison | Missing | Phase 3 |
| Full-text search baseline | Missing | Phase 3 |
