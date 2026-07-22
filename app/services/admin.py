"""Administrative job, monitoring, and normalization operations."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.job import Job, RawJob
from app.models.normalization_alias import NormalizationAlias
from app.processing.category import CATEGORIES, normalise_category
from app.processing.location import normalise_location
from app.processing.pipeline import process_raw_jobs
from app.processing.salary import annualise_salary_gbp
from app.services.embedding import build_job_text, generate_embedding

MAX_REPROCESS_BATCH = 500
SUPPORTED_CURRENCIES = {"GBP", "USD", "EUR", "INR", "AUD", "CAD", "NZD", "CHF", "SGD"}
SUPPORTED_SALARY_PERIODS = {"annual", "monthly", "weekly", "daily", "hourly"}
SEMANTIC_FIELDS = {"title", "title_clean", "description", "description_clean", "requirements", "responsibilities"}


class AdminValidationError(ValueError):
    pass


def sanitize_error(value: str | None) -> str | None:
    if not value:
        return value
    return value.replace("\r", " ").replace("\n", " ")[:500]


def resolve_alias(db: Session, kind: str, value: str | None) -> str | None:
    if not value:
        return value
    normalized = value.strip().lower()
    mapping = db.query(NormalizationAlias).filter(
        NormalizationAlias.kind == kind,
        NormalizationAlias.alias == normalized,
        NormalizationAlias.is_active.is_(True),
    ).first()
    return mapping.canonical_value if mapping else value


def save_alias(
    db: Session, kind: str, alias: str, canonical_value: str,
    alias_id: uuid.UUID | None = None, is_active: bool = True,
) -> NormalizationAlias:
    if kind not in {"category", "location"}:
        raise AdminValidationError("Alias kind must be category or location")
    normalized_alias = alias.strip().lower()
    canonical = canonical_value.strip()
    if not normalized_alias or not canonical:
        raise AdminValidationError("Alias and canonical value are required")
    if kind == "category" and canonical not in CATEGORIES:
        raise AdminValidationError("Unknown canonical category")
    if kind == "location":
        parsed = normalise_location(canonical)
        if not parsed["city"] and not parsed["country"]:
            raise AdminValidationError("Canonical location must contain a recognized city or country")
    query = db.query(NormalizationAlias).filter(
        NormalizationAlias.kind == kind, NormalizationAlias.alias == normalized_alias,
    )
    if alias_id:
        query = query.filter(NormalizationAlias.id != alias_id)
    if query.first():
        raise AdminValidationError("This alias already exists")
    mapping = db.get(NormalizationAlias, alias_id) if alias_id else NormalizationAlias(id=uuid.uuid4())
    if not mapping:
        raise AdminValidationError("Alias not found")
    mapping.kind = kind
    mapping.alias = normalized_alias
    mapping.canonical_value = canonical
    mapping.is_active = is_active
    db.add(mapping)
    db.commit()
    return mapping


def preview_normalization(db: Session, kind: str, value: str) -> str:
    mapped = resolve_alias(db, kind, value)
    if kind == "category":
        return normalise_category(mapped)
    if kind == "location":
        location = normalise_location(mapped)
        return ", ".join(filter(None, [location["city"], location["country"]])) or "Unknown"
    raise AdminValidationError("Alias kind must be category or location")


def reprocess_raw_jobs(
    db: Session, *, raw_job_id: uuid.UUID | None = None,
    ingestion_run_id: uuid.UUID | None = None, source: str | None = None,
    failed_only: bool = False, limit: int = 100,
) -> dict:
    if limit < 1 or limit > MAX_REPROCESS_BATCH:
        raise AdminValidationError(f"Batch limit must be between 1 and {MAX_REPROCESS_BATCH}")
    query = db.query(RawJob)
    if raw_job_id:
        query = query.filter(RawJob.id == raw_job_id)
    if ingestion_run_id:
        query = query.filter(RawJob.ingestion_run_id == ingestion_run_id)
    if source:
        query = query.filter(RawJob.source == source)
    if failed_only:
        query = query.filter(RawJob.processed.is_(False), RawJob.processing_attempts > 0)
    records = query.order_by(RawJob.fetched_at.asc()).limit(limit).all()
    ids = [record.id for record in records]
    if not ids:
        return {"inserted": 0, "skipped": 0, "errors": 0, "quality_avg": 0.0}
    for record in records:
        record.processed = False
    db.commit()
    return process_raw_jobs(db, limit=limit, raw_job_ids=ids)


def update_job(db: Session, job: Job, values: dict) -> Job:
    salary_min = _optional_float(values.get("salary_min", job.salary_min))
    salary_max = _optional_float(values.get("salary_max", job.salary_max))
    if salary_min is not None and salary_min < 0 or salary_max is not None and salary_max < 0:
        raise AdminValidationError("Salary values cannot be negative")
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise AdminValidationError("Minimum salary cannot exceed maximum salary")
    currency = (values.get("salary_currency", job.salary_currency) or "").upper() or None
    period = (values.get("salary_period", job.salary_period) or "").lower() or None
    if currency and currency not in SUPPORTED_CURRENCIES:
        raise AdminValidationError("Unsupported salary currency")
    if period and period not in SUPPORTED_SALARY_PERIODS:
        raise AdminValidationError("Unsupported salary period")

    semantic_changed = any(
        key in values and values[key] != getattr(job, key)
        for key in SEMANTIC_FIELDS
    )
    editable = {
        "title_clean", "company", "description", "description_clean", "requirements",
        "responsibilities", "location_city", "location_country", "remote", "category",
        "job_type", "url",
    }
    for key in editable.intersection(values):
        setattr(job, key, values[key] or None)
    job.salary_min = salary_min
    job.salary_max = salary_max
    job.salary_currency = currency
    job.salary_period = period
    job.annualised_gbp_salary = annualise_salary_gbp(
        salary_min if salary_min is not None else salary_max, currency, period,
    )
    job.salary_confidence = 1.0 if salary_min is not None or salary_max is not None else None
    if semantic_changed:
        skills = [skill.skill for skill in job.skills]
        job.embedding = generate_embedding(
            build_job_text(job.title_clean or job.title, job.description or "", skills)
        )
        job.embedded_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    db.commit()
    return job


def _optional_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AdminValidationError("Salary values must be numeric") from exc
