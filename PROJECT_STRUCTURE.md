# JobMatch AI — Project Structure

```
jobmatch/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings from .env
│   ├── database.py              # DB connection + session
│   ├── core/
│   │   └── security.py          # JWT auth, password hashing
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py              # User + Profile + NotificationPrefs
│   │   ├── job.py               # RawJob, Job, JobSkill
│   │   ├── recommendation.py    # Recommendation, SavedJob
│   │   └── notification.py      # Notification log
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py              # Register, Login, Password reset
│   │   ├── users.py             # Profile CRUD
│   │   ├── jobs.py              # Job listing, search, filter
│   │   ├── recommendations.py   # Get recommendations
│   │   └── notifications.py     # Notification preferences
│   ├── services/
│   │   ├── embedding.py         # sentence-transformers wrapper
│   │   ├── search.py            # Semantic + keyword search
│   │   ├── recommendation.py    # Scoring engine
│   │   ├── rag.py               # RAG explanation engine
│   │   └── email.py             # Email sender (SMTP)
│   ├── agents/
│   │   ├── recommendation_agent.py  # Autonomous recommendation agent
│   │   └── notification_agent.py    # Autonomous notification agent
│   ├── ingestion/
│   │   ├── base.py              # Abstract JobSource
│   │   ├── csv_source.py        # CSV dataset importer
│   │   ├── adzuna_source.py     # Adzuna API connector
│   │   └── wwr_scraper.py       # We Work Remotely RSS scraper
│   └── processing/
│       ├── pipeline.py          # Orchestrates all processors
│       ├── dedup.py             # Duplicate detection
│       ├── salary.py            # Salary standardisation
│       ├── location.py          # Location normalisation
│       ├── category.py          # Category normalisation
│       ├── title.py             # Title cleaning
│       └── skills.py            # Skill extraction
├── scripts/
│   ├── init_db.py               # Create tables + pgvector extension
│   ├── seed_csv.py              # One-command CSV import
│   ├── run_ingestion.py         # Run all sources
│   └── run_notifications.py     # Run notification agent
├── dashboard/
│   └── app.py                   # Streamlit dashboard
├── data/
│   └── (put your CSV here)
├── tests/
├── .env.example                 # Template for secrets
├── .gitignore
├── requirements.txt
├── docker-compose.yml           # Postgres + pgvector one-command
└── README.md
```
