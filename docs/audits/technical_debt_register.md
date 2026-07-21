# Technical Debt Register

**Date:** 2026-07-13
**Total Items:** 42

---

## Critical Debt (Must Fix Before Dissertation)

| ID | Category | Description | File:Line | Effort | Phase |
|----|----------|-------------|-----------|--------|-------|
| TD-01 | Infrastructure | No Alembic migration infrastructure. Schema created via `create_all()` which cannot handle evolution. | `app/database.py:29` | Large | Phase 1 |
| TD-02 | Testing | Zero automated tests. No pytest fixtures, no conftest.py, no tests/ directory. | (missing) | Large | Phase 8 |
| TD-03 | Security | Dual auth systems (FastAPI JWT + Flask session) with duplicated logic. | `app/api/auth.py`, `webapp/routes/auth.py` | Medium | Phase 6 |
| TD-04 | Security | No CSRF protection on Flask POST routes. | `webapp/routes/*.py` | Small | Phase 6 |
| TD-05 | Security | No rate limiting on any endpoint. | All route files | Small | Phase 6 |
| TD-06 | Security | No token revocation. JWT valid until expiry. | `app/core/security.py:24` | Medium | Phase 6 |
| TD-07 | Security | Hard-coded demo password hash in test script. | `scripts/test_recommend.py:46` | Small | Phase 6 |
| TD-08 | Security | No explicit HTML sanitization configuration. | `webapp/templates/` | Small | Phase 6 |

---

## High Debt (Significant Impact on Dissertation Quality)

| ID | Category | Description | File:Line | Effort | Phase |
|----|----------|-------------|-----------|--------|-------|
| TD-09 | Performance | No HNSW index on embedding column. Flat scan for all vector queries. | `app/models/job.py:72` | Medium | Phase 3 |
| TD-10 | Performance | No PostgreSQL full-text search. Keyword baseline uses ILIKE. | `app/services/search.py:164` | Medium | Phase 3 |
| TD-11 | Performance | No cross-encoder reranking capability. | (missing) | Large | Phase 3 |
| TD-12 | Data Model | No database indexes beyond PKs and dedup_hash. | `app/models/*.py` | Small | Phase 1 |
| TD-13 | Data Model | No timezone-aware datetimes. All naive UTC. | `app/models/*.py` | Small | Phase 1 |
| TD-14 | Data Model | No `processing_error` table. Failed records silently marked processed. | `app/processing/pipeline.py:127` | Small | Phase 1 |
| TD-15 | Data Model | `IngestionRun` model defined but never written. | `app/models/ingestion_run.py` | Small | Phase 2 |
| TD-16 | Architecture | Recommendation agent has no structured state or decision audit trail. | `app/agents/recommendation_agent.py` | Medium | Phase 5 |
| TD-17 | Architecture | RAG has no output validation. LLM may hallucinate facts. | `app/services/rag.py:139` | Medium | Phase 5 |
| TD-18 | Architecture | No user interaction tracking (impressions, clicks, saves). | (missing) | Medium | Phase 4 |
| TD-19 | Configuration | Hard-coded scoring weights. Not configurable or versioned. | `app/services/recommendation.py:22` | Small | Phase 4 |
| TD-20 | UX | No profile completeness calculation or guidance. | `app/api/recommendations.py:81` | Small | Phase 4 |
| TD-21 | Architecture | No hard constraint separation in recommendations. | `app/services/recommendation.py:65` | Medium | Phase 4 |
| TD-22 | NLP | Skill extraction is dictionary-only. No aliases, confidence, or essential/desirable. | `app/processing/skills.py:104` | Medium | Phase 2 |
| TD-23 | Data Quality | No job quality scoring. | (missing) | Medium | Phase 2 |
| TD-24 | Reliability | Reed source uses synchronous HTTP despite httpx availability. | `app/ingestion/reed_source.py:60` | Small | Phase 2 |

---

## Medium Debt (Should Fix for Production Quality)

| ID | Category | Description | File:Line | Effort | Phase |
|----|----------|-------------|-----------|--------|-------|
| TD-25 | Observability | No structured logging. All output via `print()`. | All files | Medium | Phase 6 |
| TD-26 | API | No CORS middleware on FastAPI. | `app/main.py:10` | Small | Phase 6 |
| TD-27 | Monitoring | No health check endpoint for Flask. | `webapp/app.py` | Small | Phase 8 |
| TD-28 | Testing | Evaluation uses binary relevance (0/1). No graded labels. | `scripts/run_evaluation.py:99` | Small | Phase 7 |
| TD-29 | Metrics | No MRR metric. | `app/evaluation/metrics.py` | Small | Phase 7 |
| TD-30 | Metrics | No ablation study capability. | (missing) | Large | Phase 7 |
| TD-31 | Python | `datetime.utcnow()` deprecated in Python 3.12+. | 5+ locations | Small | Phase 1 |
| TD-32 | Hygiene | `test_recommend.py` destructively overwrites real profiles. | `scripts/test_recommend.py:74` | Small | Phase 8 |
| TD-33 | Data Model | No Alembic env.py or script.py.mako. | (missing) | Small | Phase 1 |
| TD-34 | Documentation | README references Streamlit; actual frontend is Flask. | `README.md:19` | Small | Phase 8 |
| TD-35 | Dependencies | langchain packages in requirements but unused. | `requirements.txt:33` | Small | Phase 8 |
| TD-36 | Config | .gitignore not verified for .env exclusion. | `.gitignore` | Small | Phase 8 |

---

## Low Debt (Nice to Fix)

| ID | Category | Description | File:Line | Effort | Phase |
|----|----------|-------------|-----------|--------|-------|
| TD-37 | Code Quality | No `__all__` in package __init__.py files. | Various | Small | Phase 8 |
| TD-38 | Portability | Emoji in print statements may not render on all terminals. | Various scripts | Small | Phase 8 |
| TD-39 | Type Safety | No py.typed marker or mypy config. | (missing) | Small | Phase 8 |
| TD-40 | Code Quality | Streamlit dashboard directory appears superseded. | `dashboard/` | Small | Phase 8 |
| TD-41 | Code Quality | No static type checking in CI. | (missing) | Small | Phase 8 |
| TD-42 | Documentation | Some __init__.py files are empty with no exports. | Various | Small | Phase 8 |

---

## Debt by Phase

| Phase | Items | IDs |
|-------|-------|-----|
| Phase 1 | 7 | TD-01, TD-12, TD-13, TD-14, TD-31, TD-33, TD-15 |
| Phase 2 | 5 | TD-15, TD-22, TD-23, TD-24, TD-15 |
| Phase 3 | 3 | TD-09, TD-10, TD-11 |
| Phase 4 | 4 | TD-18, TD-19, TD-20, TD-21 |
| Phase 5 | 2 | TD-16, TD-17 |
| Phase 6 | 8 | TD-03, TD-04, TD-05, TD-06, TD-07, TD-08, TD-25, TD-26 |
| Phase 7 | 3 | TD-28, TD-29, TD-30 |
| Phase 8 | 10 | TD-02, TD-27, TD-32, TD-34, TD-35, TD-36, TD-37, TD-38, TD-39, TD-40, TD-41, TD-42 |

---

## Effort Estimates

| Effort | Count | Description |
|--------|-------|-------------|
| Small | 24 | < 2 hours, isolated change |
| Medium | 12 | 2-8 hours, may affect multiple files |
| Large | 6 | > 8 hours, architectural change |
