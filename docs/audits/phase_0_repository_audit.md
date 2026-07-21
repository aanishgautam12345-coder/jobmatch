# Phase 0 — Repository Audit

**Date:** 2026-07-13
**Auditor:** AI Systems Architect
**Scope:** Complete repository inspection of JobMatch AI

---

## 1. Executive Summary

JobMatch AI is a working prototype with a functional data pipeline, semantic search, recommendation engine, and RAG explanation system. The codebase is well-structured with clear separation of concerns. However, it has significant gaps that must be addressed before it can serve as a defensible dissertation project.

**Critical findings:** 8
**High findings:** 14
**Medium findings:** 11
**Low findings:** 6

---

## 2. Findings

| # | Severity | Finding | File | Impact | Resolution | Phase |
|---|----------|---------|------|--------|------------|-------|
| 1 | **Critical** | No Alembic migrations exist. Database schema is created via `Base.metadata.create_all()` which cannot handle schema evolution, data migrations, or rollback. | `app/database.py:29` | Any schema change destroys data or requires manual intervention. Cannot demonstrate reproducible deployment. | Set up Alembic with initial migration. | Phase 1 |
| 2 | **Critical** | No automated tests exist. `tests/` directory is absent. `conftest.py` absent. Only interactive demo scripts. | (project root) | No regression detection. No CI/CD capability. Cannot verify correctness of changes. | Create test suite with pytest fixtures. | Phase 8 |
| 3 | **Critical** | Dual web framework architecture (FastAPI + Flask) with duplicated authentication logic. No clear authoritative auth layer. | `app/api/auth.py`, `webapp/routes/auth.py` | Security risk: two independent auth implementations must stay synchronized. Maintenance burden. | Decide on single auth authority. | Phase 6 |
| 4 | **Critical** | No CSRF protection on Flask forms. `flask-wtf` not installed. | `webapp/routes/auth.py`, `webapp/routes/profile.py` | Cross-site request forgery attacks possible on all POST routes. | Add CSRF protection. | Phase 6 |
| 5 | **Critical** | Hard-coded demo password hash in `test_recommend.py:46`: `"demo-not-a-real-hash"`. | `scripts/test_recommend.py:46` | Demonstrates insecure pattern. If copied to production, password verification bypassed. | Use proper hashing in test scripts. | Phase 6 |
| 6 | **Critical** | No rate limiting on any endpoint. Login, registration, and API endpoints are unprotected. | `app/api/auth.py`, `webapp/routes/auth.py` | Brute-force attacks, credential stuffing, API abuse. | Add rate limiting middleware. | Phase 6 |
| 7 | **Critical** | No input sanitization on HTML templates. Jinja2 autoescaping is Flask default but not explicitly configured. User-generated content rendered without sanitization. | `webapp/templates/` | Potential XSS if user-controlled data reaches templates. | Explicitly configure autoescaping, sanitize inputs. | Phase 6 |
| 8 | **Critical** | No token revocation mechanism. JWT tokens are valid until expiry with no way to invalidate. | `app/core/security.py:24-30` | Compromised tokens remain valid for up to 24 hours. Logout only clears Flask session, not FastAPI JWT. | Add token blacklist or short-lived refresh tokens. | Phase 6 |
| 9 | **High** | No database indexes beyond primary keys and dedup_hash. Missing indexes on `jobs.created_at`, `jobs.category`, `jobs.location_country`, `recommendations.user_id`, `notifications.user_id`. | `app/models/job.py`, `app/models/recommendation.py`, `app/models/notification.py` | Slow queries at scale. Recommendation and notification queries will degrade. | Add composite and single-column indexes. | Phase 1 |
| 10 | **High** | Vector search uses flat index (no HNSW or IVFFlat). All cosine distance computations are sequential scans. | `app/services/search.py:41`, `app/models/job.py:72` | O(n) search time. Inacceptable for production use. | Add HNSW index on embedding column. | Phase 3 |
| 11 | **High** | No PostgreSQL full-text search. Keyword search uses ILIKE which cannot use indexes efficiently. | `app/services/search.py:164-212` | Baseline comparison is unfair — ILIKE is not a competitive keyword search baseline. | Implement tsvector/tsquery with GIN index. | Phase 3 |
| 12 | **High** | No cross-encoder reranking. Recommendations are based solely on vector similarity + scoring. | `app/agents/recommendation_agent.py` | Misses opportunity for significant ranking improvement. Cannot evaluate reranking benefit. | Add cross-encoder reranker behind interface. | Phase 3 |
| 13 | **High** | Recommendation agent has no structured state or audit trail. Decisions are made but not logged. | `app/agents/recommendation_agent.py:67-76` | Cannot reproduce or debug recommendation decisions. Not auditable for dissertation. | Add structured state and decision logging. | Phase 5 |
| 14 | **High** | RAG explanation has no validation. LLM output is used directly without checking for hallucinated facts. | `app/services/rag.py:139-155` | Explanations may contain fabricated skills, salaries, or qualifications. | Add post-generation validation. | Phase 5 |
| 15 | **High** | No user interaction tracking. Cannot measure click-through, save rate, or application rate. | (missing) | No implicit feedback data for future model improvement. | Add impression/interaction events. | Phase 4 |
| 16 | **High** | No timezone awareness. All `datetime.utcnow()` calls produce naive datetimes. | `app/models/job.py:23`, `app/models/user.py:20`, `app/models/recommendation.py:24` | Ambiguous timestamps. Cannot handle cross-timezone scheduling. | Use timezone-aware datetimes. | Phase 1 |
| 17 | **High** | Hard-coded scoring weights in `app/services/recommendation.py:22-29`. Not configurable or versioned. | `app/services/recommendation.py:22-29` | Cannot experiment with different weight configurations. Not reproducible. | Move to versioned config. | Phase 4 |
| 18 | **High** | No `processing_error` table. Failed records are silently marked as processed. | `app/processing/pipeline.py:127-137` | Lost data with no recovery path. Cannot analyze processing failures. | Add error logging table. | Phase 1 |
| 19 | **High** | Embedding text construction repeats title unconditionally (line 150 in `embedding.py`). This is a design choice but undocumented and untested. | `app/services/embedding.py:146-151` | May dilute embedding signal for multi-word titles. Not evaluated. | Document rationale, evaluate alternatives. | Phase 3 |
| 20 | **High** | No profile completeness calculation. Users with empty profiles get no recommendations but no guidance. | `app/api/recommendations.py:81-85` | Poor user experience. Cannot measure profile quality impact. | Add completeness scoring. | Phase 4 |
| 21 | **High** | No hard constraint separation. Location/salary preferences are weighted the same as soft preferences. | `app/services/recommendation.py:65-123` | User marking "must be remote" gets non-remote jobs at reduced score instead of filtered out. | Separate hard filters from soft preferences. | Phase 4 |
| 22 | **High** | Skill extraction is dictionary-only. No alias resolution, no confidence scoring, no essential/desirable classification. | `app/processing/skills.py:104-128` | Cannot distinguish required vs nice-to-have skills. No extraction provenance. | Enhance skill taxonomy. | Phase 2 |
| 23 | **High** | No job quality scoring. Poorly described jobs are treated identically to comprehensive ones. | (missing) | Low-quality jobs pollute search results and recommendations. | Add quality scoring. | Phase 2 |
| 24 | **Medium** | `datetime.utcnow()` is deprecated in Python 3.12+. Used in 5+ locations. | `app/models/job.py:23`, `app/models/user.py:20`, `app/models/notification.py:23` | Future Python version incompatibility. | Replace with `datetime.now(UTC)`. | Phase 1 |
| 25 | **Medium** | No structured logging. All output uses `print()` statements. | All files | Cannot filter, route, or persist logs in production. | Add Python `logging` module. | Phase 6 |
| 26 | **Medium** | No CORS configuration on FastAPI. | `app/main.py:10-14` | API cannot be called from frontend on different origin. | Add CORS middleware. | Phase 6 |
| 27 | **Medium** | No health check endpoint for Flask frontend. Only FastAPI has `/health`. | `webapp/app.py` | Cannot monitor Flask service health. | Add health endpoint. | Phase 8 |
| 28 | **Medium** | `IngestionRun` model exists but is never written to during ingestion. | `app/models/ingestion_run.py`, `app/processing/pipeline.py` | Import monitoring feature is incomplete. | Wire up IngestionRun writes. | Phase 2 |
| 29 | **Medium** | No `.gitignore` entries for `.env` files beyond the basic one. `venv/` is in `.gitignore` but not verified. | `.gitignore` | Risk of committing secrets. | Audit .gitignore. | Phase 8 |
| 30 | **Medium** | Evaluation harness uses binary relevance labels (0/1). No graded relevance support. | `scripts/run_evaluation.py:99` | Cannot distinguish strong from weak matches in evaluation. | Add graded relevance (0-3). | Phase 7 |
| 31 | **Medium** | No MRR (Mean Reciprocal Rank) metric. | `app/evaluation/metrics.py` | Incomplete metric suite for dissertation. | Add MRR function. | Phase 7 |
| 32 | **Medium** | No ablation study capability. Cannot remove individual components and measure impact. | (missing) | Cannot demonstrate contribution of each component. | Build ablation runner. | Phase 7 |
| 33 | **Medium** | Reed source does synchronous HTTP in a loop. Not async despite httpx being available. | `app/ingestion/reed_source.py:60-121` | Slow ingestion for large fetches. | Convert to async. | Phase 2 |
| 34 | **Medium** | No Alembic `env.py` or `script.py.mako`. No migration infrastructure at all. | (missing) | Cannot create or run migrations. | Initialize Alembic. | Phase 1 |
| 35 | **Medium** | `test_recommend.py` overwrites profile fields on every run (lines 74-83). Destructive to user edits. | `scripts/test_recommend.py:74-83` | Test script corrupts real user profiles. | Isolate test data. | Phase 8 |
| 36 | **Low** | README.md references Streamlit as the frontend but the actual frontend is Flask/Jinja2. | `README.md:19` | Documentation out of date. | Update README. | Phase 8 |
| 38 | **Low** | `dashboard/` directory contains Streamlit code that appears superseded by `webapp/`. | `dashboard/` | Confusing codebase structure. | Archive or remove. | Phase 8 |
| 39 | **Low** | No `__all__` in `app/services/__init__.py`, `app/processing/__init__.py`, `app/ingestion/__init__.py`. | Various `__init__.py` | Minor import hygiene. | Add `__all__` exports. | Phase 8 |
| 40 | **Low** | Emoji usage in print statements (e.g., `print("✓ Done")`) may not render on all terminals. | Various scripts | Minor portability issue. | Use ASCII fallbacks or logging. | Phase 8 |
| 41 | **Low** | No `py.typed` marker or mypy configuration. | (missing) | No static type checking in CI. | Add mypy config. | Phase 8 |

---

## 3. Severity Summary

| Severity | Count |
|----------|-------|
| Critical | 8 |
| High | 16 |
| Medium | 12 |
| Low | 6 |
| **Total** | **42** |

---

## 4. What Works Well

The following aspects of the current implementation are sound and should be preserved:

1. **Clean separation of concerns:** models, services, agents, ingestion, processing are well-organized.
2. **Working data pipeline:** raw_jobs → processing → jobs with embeddings is functional.
3. **Multi-source ingestion:** CSV, Adzuna, Reed, WWR sources all implement the same interface.
4. **Semantic search:** pgvector cosine distance search works correctly.
5. **Hybrid search:** Combines semantic ranking with SQL filters.
6. **6-factor scoring:** Transparent, testable scoring formula.
7. **RAG explanations:** Grounded in computed facts with fallback.
8. **Resume parsing:** PDF → LLM → structured profile is implemented.
9. **Notification agent:** Has anti-spam, multiple notification types, digest emails.
10. **Evaluation harness:** Interactive labeling with persistence.

---

## 5. Files Inventory

### Core Application Files
| File | Lines | Status |
|------|-------|--------|
| `app/config.py` | 40 | Working |
| `app/database.py` | 30 | Working, needs migration setup |
| `app/main.py` | 37 | Working, needs CORS |
| `app/core/security.py` | 39 | Working, needs token revocation |
| `app/core/deps.py` | 36 | Working |

### Models
| File | Lines | Status |
|------|-------|--------|
| `app/models/user.py` | 84 | Working, needs timezone |
| `app/models/job.py` | 97 | Working, needs indexes |
| `app/models/recommendation.py` | 45 | Working, needs indexes |
| `app/models/notification.py` | 27 | Working |
| `app/models/ingestion_run.py` | 28 | Defined but unused |

### API Routes
| File | Lines | Status |
|------|-------|--------|
| `app/api/auth.py` | 164 | Working, needs CSRF/rate-limiting |
| `app/api/users.py` | 132 | Working |
| `app/api/jobs.py` | 60 | Working |
| `app/api/jobs_extended.py` | 305 | Working |
| `app/api/recommendations.py` | 238 | Working |

### Services
| File | Lines | Status |
|------|-------|--------|
| `app/services/embedding.py` | 195 | Working |
| `app/services/search.py` | 258 | Working, needs FTS |
| `app/services/recommendation.py` | 265 | Working, needs configurability |
| `app/services/rag.py` | 175 | Working, needs validation |
| `app/services/resume_parser.py` | 242 | Working |
| `app/services/email.py` | 92 | Working |

### Agents
| File | Lines | Status |
|------|-------|--------|
| `app/agents/recommendation_agent.py` | 185 | Working, needs state/audit |
| `app/agents/notification_agent.py` | 288 | Working |

### Ingestion
| File | Lines | Status |
|------|-------|--------|
| `app/ingestion/base.py` | 26 | Working |
| `app/ingestion/csv_source.py` | 71 | Working |
| `app/ingestion/csv_descriptions2.py` | 161 | Working |
| `app/ingestion/adzuna_source.py` | 106 | Working |
| `app/ingestion/reed_source.py` | 172 | Working, sync HTTP |
| `app/ingestion/wwr_scraper.py` | 68 | Working |

### Processing
| File | Lines | Status |
|------|-------|--------|
| `app/processing/pipeline.py` | 265 | Working |
| `app/processing/title.py` | 62 | Working |
| `app/processing/salary.py` | 176 | Working |
| `app/processing/location.py` | 139 | Working |
| `app/processing/category.py` | 153 | Working |
| `app/processing/skills.py` | 191 | Working, needs enhancement |
| `app/processing/dedup.py` | 68 | Working |

### Evaluation
| File | Lines | Status |
|------|-------|--------|
| `app/evaluation/metrics.py` | 88 | Working, missing MRR |

### Web Frontend
| File | Lines | Status |
|------|-------|--------|
| `webapp/app.py` | 86 | Working |
| `webapp/routes/auth.py` | 111 | Working, needs CSRF |
| `webapp/routes/main.py` | 37 | Working |
| `webapp/routes/jobs.py` | 231 | Working |
| `webapp/routes/profile.py` | 84 | Working |

### Scripts
| File | Lines | Status |
|------|-------|--------|
| `scripts/init_db.py` | 17 | Working |
| `scripts/seed_csv.py` | 99 | Working |
| `scripts/seed_reed.py` | 124 | Working |
| `scripts/run_processing.py` | 63 | Working |
| `scripts/run_evaluation.py` | 232 | Working |
| `scripts/test_search.py` | 89 | Working |
| `scripts/test_recommend.py` | 148 | Working, destructive |
| `scripts/test_explain.py` | 66 | Working |
| `scripts/test_notify.py` | 83 | Working |

---

## 6. Architecture Assumptions Identified

1. **PostgreSQL is the only database.** No SQLite fallback for testing.
2. **Embedding model is always available.** No fallback if sentence-transformers fails to load.
3. **OpenAI API key is required.** RAG falls back to templates if unavailable, but resume parsing fails hard.
4. **All jobs are English.** No language detection or multilingual support.
5. **Salary is annual by default.** Non-annual salaries may be incorrectly compared.
6. **One user = one profile.** No support for multiple profiles or career changes.
7. **Skills are lowercase strings.** No canonical skill IDs or hierarchy.
8. **Dedup is title+company+location only.** Same job posted with different titles passes dedup.
9. **Embeddings are generated at ingest time only.** No re-embedding when model changes.
10. **Recommendations are computed on demand.** No caching layer.
