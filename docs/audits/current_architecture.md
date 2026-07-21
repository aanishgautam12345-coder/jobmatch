# Current Architecture

**Date:** 2026-07-13
**Status:** Working prototype

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTS                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ Browser  │  │ API User │  │ Schedule │                      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
└───────┼──────────────┼─────────────┼────────────────────────────┘
        │              │             │
        ▼              ▼             ▼
┌───────────────┐ ┌───────────┐ ┌──────────┐
│  Flask Web    │ │ FastAPI   │ │ APScheduler│
│  (port 5000)  │ │ (port 8000)│ │ (in-proc) │
└───────┬───────┘ └─────┬─────┘ └─────┬────┘
        │               │             │
        │    ┌──────────┴─────────────┘
        │    │
        ▼    ▼
┌─────────────────────────────────────┐
│         Shared Services Layer        │
│  ┌──────────┐  ┌──────────────────┐ │
│  │ Models   │  │ Services          │ │
│  │ (SQLAlch)│  │ (Embedding,Search │ │
│  │          │  │  RAG,Recommend)   │ │
│  └──────────┘  └──────────────────┘ │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│     PostgreSQL 16 + pgvector         │
│  ┌──────────────────────────────┐   │
│  │ raw_jobs | jobs | job_skills │   │
│  │ users | user_profiles        │   │
│  │ recommendations | saved_jobs │   │
│  │ notifications                │   │
│  │ ingestion_runs               │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```

---

## 2. Data Flow

### 2.1 Ingestion Flow
```
External Sources                    Internal Pipeline
─────────────                       ─────────────────
CSV Dataset ─┐
Adzuna API ──┤  fetch()     RawJobRecord    process_raw_jobs()
Reed API ────┤ ──────────►  raw_jobs ───►  ┌─────────────────┐
WWR RSS ─────┘                │           │ 1. Title clean   │
                              │           │ 2. Salary parse  │
                              │           │ 3. Location norm │
                              │           │ 4. Category map  │
                              │           │ 5. Skill extract │
                              │           │ 6. Dedup check   │
                              │           │ 7. Embed (BGE)   │
                              │           └────────┬────────┘
                              │                    │
                              │                    ▼
                              │           jobs + job_skills
                              │           (with 768d vectors)
```

### 2.2 Search Flow
```
User Query ──► Generate Embedding (BGE, is_query=True)
                    │
                    ▼
            pgvector cosine distance
            SELECT *, (1 - distance) AS similarity
            ORDER BY distance
            LIMIT k
                    │
                    ▼
            Filtered Results
```

### 2.3 Recommendation Flow
```
User Profile
    │
    ├──► Profile Embedding (BGE, is_query=True)
    │        │
    │        ▼
    │    Vector Search (30 candidates, expand to 80 if weak)
    │        │
    │        ▼
    │    Score Each Candidate (6 factors)
    │        │
    │        ▼
    │    Filter (score ≥ 0.15) → Rank → Top N
    │
    └──► Persist Recommendations
```

### 2.4 Explanation Flow
```
Recommendation Request
    │
    ├──► Retrieve Evidence (profile + job + breakdown)
    │
    ├──► Build Prompt (facts only, no invention)
    │
    ├──► OpenAI (GPT, temp=0.3)
    │
    ├──► Cache Result
    │
    └──► Return Explanation
```

---

## 3. Database Schema

```
raw_jobs (1) ──── (0..1) jobs (1) ──── (0..*) job_skills
                       │
                       │
                       ├── (0..*) recommendations ──── users
                       │                                      │
                       ├── (0..*) saved_jobs ────────────────┤
                       │                                      │
                       ├── (0..*) notifications ─────────────┘
                       │
                       └── (0..1) ingestion_runs (not yet wired)

users (1) ──── (1) user_profiles
           └── (1) notification_preferences
```

### Key Relationships
- `jobs.raw_job_id` → `raw_jobs.id` (nullable FK)
- `job_skills.job_id` → `jobs.id` (CASCADE)
- `recommendations.user_id` → `users.id` (CASCADE)
- `recommendations.job_id` → `jobs.id` (CASCADE)
- `saved_jobs.user_id` → `users.id` (CASCADE)
- `saved_jobs.job_id` → `jobs.id` (CASCADE)
- `notifications.user_id` → `users.id` (CASCADE)
- `notifications.job_id` → `jobs.id` (CASCADE)
- `user_profiles.user_id` → `users.id` (CASCADE, unique)
- `notification_preferences.user_id` → `users.id` (CASCADE, unique)

---

## 4. Technology Stack

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Language | Python | 3.10+ | Core runtime |
| API Framework | FastAPI | 0.115.0 | REST API |
| Web Framework | Flask | 3.0.3 | Frontend |
| ORM | SQLAlchemy | 2.0.35 | Database access |
| Database | PostgreSQL | 16 | Primary storage |
| Vector Extension | pgvector | 0.3.5 | Similarity search |
| Embedding Model | BAAI/bge-base-en-v1.5 | — | 768d vectors |
| Embedding Library | sentence-transformers | 3.1.0 | Model interface |
| LLM Provider | OpenAI | — | API |
| LLM Model | gpt-5.6-sol (configurable) | — | Explanation generation |
| Auth (API) | JWT (python-jose) | 3.3.0 | Token-based auth |
| Auth (Web) | Flask-Login | 0.6.3 | Session-based auth |
| Password Hashing | passlib (bcrypt) | 1.7.4 | Credential storage |
| PDF Parsing | pypdf | 4.3.1 | Resume text extraction |
| HTTP Client | httpx | 0.27.2 | API calls |
| Fuzzy Matching | rapidfuzz | 3.9.7 | Near-duplicate detection |
| Container | Docker Compose | — | Database deployment |

---

## 5. API Endpoints

### FastAPI (port 8000)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | Health check |
| POST | `/api/auth/register` | No | Create account |
| POST | `/api/auth/login` | No | Authenticate |
| POST | `/api/auth/forgot` | No | Request reset |
| POST | `/api/auth/reset` | No | Reset password |
| GET | `/api/users/me/profile` | JWT | Get profile |
| PUT | `/api/users/me/profile` | JWT | Update profile |
| PUT | `/api/users/me/notifications` | JWT | Update prefs |
| GET | `/api/jobs/search/semantic` | No | Semantic search |
| GET | `/api/jobs/search/keyword` | No | Keyword search |
| GET | `/api/jobs/search/hybrid` | No | Hybrid search |
| GET | `/api/jobs/{id}/similar` | No | Similar jobs |
| GET | `/api/jobs/saved` | JWT | Saved jobs |
| POST | `/api/jobs/saved/{id}` | JWT | Save job |
| DELETE | `/api/jobs/saved/{id}` | JWT | Unsave job |
| GET | `/api/jobs/search/skills` | No | Skill search |
| GET | `/api/jobs/search/company` | No | Company search |
| GET | `/api/jobs/recent` | No | Recent jobs |
| GET | `/api/jobs/search/similar-skills` | No | Semantic skill search |
| GET | `/api/recommendations/me/recommendations` | JWT | Get recommendations |
| GET | `/api/recommendations/me/recommendations/{id}` | JWT | Single recommendation |
| POST | `/api/recommendations/explain/{id}` | JWT | Generate explanation |

### Flask (port 5000)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | No* | Landing or home |
| GET/POST | `/auth/register` | No | Registration |
| GET/POST | `/auth/login` | No | Login |
| GET | `/auth/logout` | Session | Logout |
| GET | `/jobs/search` | Session | Search page |
| GET | `/jobs/recommendations` | Session | Recommendations |
| GET | `/jobs/{id}` | Session | Job detail |
| GET | `/jobs/explain/{id}` | Session | AJAX explanation |
| POST | `/jobs/save/{id}` | Session | AJAX save |
| POST | `/jobs/unsave/{id}` | Session | AJAX unsave |
| GET | `/jobs/saved` | Session | Saved jobs |
| GET | `/jobs/recent` | Session | Recent jobs |
| GET/POST | `/profile/` | Session | Profile edit |
| POST | `/profile/upload-resume` | Session | Resume upload |

*Redirects to landing page if unauthenticated.

---

## 6. Scoring Model

```
match_score = 0.40 × semantic_similarity
            + 0.20 × skill_overlap
            + 0.15 × location_fit
            + 0.10 × salary_fit
            + 0.10 × experience_fit
            + 0.05 × job_type_fit
```

| Factor | Range | Neutral Value | Notes |
|--------|-------|---------------|-------|
| semantic_similarity | 0–1 | — | Cosine similarity |
| skill_overlap | 0–1 | 0.5 (no skills) | |intersection| / |job_skills| |
| location_fit | 0–1 | 0.5 (no pref) | 1.0=remote/exact, 0.6=country |
| salary_fit | 0–1 | 0.5 (no pref) | With currency conversion |
| experience_fit | 0–1 | 0.5 (unknown) | -0.25 per level distance |
| job_type_fit | 0–1 | 0.5 (no pref) | Binary match |

---

## 7. Model Parameters

### Recommendation Agent
- Initial candidate pool: 30
- Expanded candidate pool: 80
- Quality threshold: 0.35
- Minimum acceptable score: 0.15

### Notification Agent
- Max notifications per run: 5
- Default lookback: 24 hours
- Saved job similarity threshold: 0.85

### Embedding
- Model: BAAI/bge-base-en-v1.5
- Dimensions: 768
- Query prefix: "Represent this sentence: "
- Normalization: L2
- Batch size: 32

### RAG
- Model: llama-3.1-8b-instant
- Temperature: 0.3
- Max tokens: 200
- Cache: 256 entries (in-memory)

---

## 8. Missing Components

| Component | Status | Impact |
|-----------|--------|--------|
| Alembic migrations | Not present | No schema evolution |
| Automated tests | Not present | No regression detection |
| CORS configuration | Not present | Cross-origin blocked |
| Rate limiting | Not present | Abuse possible |
| CSRF protection | Not present | Form attacks possible |
| Structured logging | Not present | No observability |
| Health checks (Flask) | Not present | No monitoring |
| Token revocation | Not present | No logout for JWT |
| Cross-encoder reranker | Not present | No reranking |
| Full-text search | Not present | Weak baseline |
| HNSW index | Not present | Slow vector search |
| User interactions | Not present | No feedback loop |
| Job quality scoring | Not present | No quality filtering |
| Recommendation audit | Not present | Not reproducible |
| Explanation validation | Not present | Hallucination risk |
