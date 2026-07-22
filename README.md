# JobMatch AI

**AI-Powered Job Vacancy Aggregator & Personalised Notification System**

An intelligent job aggregation and personalised recommendation platform that uses
semantic search, RAG explanations, and autonomous AI agents to help job seekers
discover relevant employment opportunities.

---

## Tech Stack (100% free)

| Layer | Technology |
|---|---|
| Backend API | Python + FastAPI |
| Frontend | Python + Flask (Jinja2 templates) |
| Database | PostgreSQL 16 + pgvector |
| Embeddings | BAAI/bge-base-en-v1.5 (768d) |
| LLM | OpenAI (GPT) |
| Data Sources | Adzuna API + Reed API + We Work Remotely RSS |

---

## Quick Start

### 1. Prerequisites
- Python 3.11+
- Docker (for PostgreSQL + pgvector)
- Git

### 2. Clone and setup
```bash
git clone <your-repo-url>
cd jobmatch

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Start the database
```bash
docker compose up -d
```
This starts PostgreSQL 16 with the pgvector extension on port 5432.

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env with your actual keys (Adzuna, OpenAI, etc.)
```

The LLM feature (RAG explanations + resume parsing) requires an OpenAI API key.
- Set `OPENAI_API_KEY` in `.env` — get one at https://platform.openai.com/api-keys
- Optionally set `OPENAI_MODEL` (default: `gpt-5.6-sol`)
- ChatGPT subscriptions and OpenAI API billing are separate; the API key is not the same as a ChatGPT login.

### 5. Run database migrations
```bash
alembic upgrade head
```

### 6. Seed data
```bash
# Import CSV dataset
python -m scripts.seed_csv                  # all rows
python -m scripts.seed_csv --limit 500      # first 500 rows (for testing)
```

### 7. Start the API
```bash
uvicorn app.main:app --reload
# Open http://localhost:8000/docs for the API playground
```

### 8. Start the Flask frontend
```bash
python run.py
# Open http://localhost:5000
```

### 9. Run the evaluation harness
```bash
python -m scripts.run_evaluation           # label + evaluate
python -m scripts.run_ablation             # ablation study
```

### 10. Run tests
```bash
python -m pytest tests/ -v
```

## Configuration

Copy `.env.example` to `.env` and set values for the services you use. Never
commit `.env`. Important settings include:

- `DATABASE_URL`, `SECRET_KEY`, `APP_BASE_URL`
- `OPENAI_API_KEY` and `OPENAI_MODEL`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`
- `PASSWORD_RESET_EXPIRY_MINUTES` (15 by default)
- `SCHEDULER_ENABLED`, scheduler timezone and delivery times
- `NOTIFICATION_MAX_RETRIES`, `NOTIFICATION_DIGEST_LIMIT`
- `RECOMMENDED_SEARCH_THRESHOLD`

## Password Recovery

The Flask login page links to `/auth/forgot-password`. Existing active accounts
receive a purpose-restricted, single-use reset link through SMTP. The link uses
`APP_BASE_URL` and expires after `PASSWORD_RESET_EXPIRY_MINUTES`. Responses are
identical for known and unknown addresses. If SMTP is unavailable, the request
still receives the generic response and no delivery is claimed.

## Administrator Setup

Run migrations first, then explicitly grant an existing trusted account admin
status in PostgreSQL:

```sql
UPDATE users SET is_admin = TRUE WHERE email = 'administrator@example.com';
```

Admin status is never inferred from an email address. Administrators can use
`/admin/ingestion-runs`, `/admin/jobs`, `/admin/reprocess`, and `/admin/aliases`.
The equivalent JSON API is under `/api/admin`. Reprocessing requires confirmation
and has a maximum batch size of 500; original raw payloads are retained.

## Notification Scheduler

Notifications run in one dedicated process, not inside Flask or FastAPI workers:

```bash
python -m scripts.run_scheduler
```

Set `SCHEDULER_ENABLED=true` only for that process. Instant, daily, and weekly
jobs respect each user's profile preference. Notification rows are reserved as
pending and become sent only after SMTP succeeds; failed attempts are retained
for bounded retry. Saved-job and changed-top-recommendation updates are included
in email delivery. Configure SMTP separately; automated tests mock delivery and
do not prove that real credentials work.

## Recommended Search

Signed-in Flask users can enable **Recommended for me** on manual job search.
The filter requires a usable profile, keeps location, remote, category, and
salary filters, blends query relevance with the existing recommendation score,
and displays a profile match percentage. FastAPI clients can pass
`recommended=true` to `/api/jobs/search/hybrid` with a bearer token.

## Verification

```bash
alembic upgrade head
python -m compileall -q app webapp scripts tests
python -m pytest -q
git diff --check
```

---

## Build Order

1. ✅ Project scaffold, DB schema, CSV importer
2. ✅ Job processing pipeline (dedup, normalise, embed)
3. ✅ Adzuna API connector + WWR scraper
4. ✅ Semantic search (pgvector)
5. ✅ User management + auth
6. ✅ Recommendation agent + scoring
7. ✅ RAG explanation engine
8. ✅ Notification agent
9. ✅ Flask frontend (Jinja2 templates)
10. ✅ Evaluation harness + results
11. ✅ UK data ingestion pipeline (Phase 2)
12. ✅ Search infrastructure + hybrid search (Phase 3)
13. ✅ Personalisation + hard constraints (Phase 4)
14. ✅ Agent audit trail + RAG validation (Phase 5)
15. ✅ Security hardening (Phase 6)
16. ✅ Evaluation metrics upgrade + ablation (Phase 7)
17. ✅ Test suite + cleanup (Phase 8)
