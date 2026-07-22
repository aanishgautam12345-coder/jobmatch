"""Processing Pipeline — the heart of data transformation.

Takes raw_jobs → processes each through all processors → writes clean jobs
with embeddings to the jobs table.

Includes:
- Quality scoring for each processed job
- IngestionRun tracking for each pipeline execution
- ProcessingError logging for debugging
- Structured logging throughout

Usage:
    python -m scripts.run_processing
    python -m scripts.run_processing --limit 100
"""

import logging
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.job import RawJob, Job, JobSkill
from app.models.job_posting import JobPosting
from app.models.normalization_alias import NormalizationAlias
from app.models.ingestion_run import IngestionRun
from app.models.processing_error import ProcessingError
from app.processing.title import clean_title
from app.processing.salary import parse_salary
from app.processing.location import normalise_location
from app.processing.category import normalise_category
from app.processing.skills import extract_skills
from app.processing.dedup import generate_dedup_hash
from app.processing.quality import score_job
from app.services.embedding import generate_embedding, build_job_text

logger = logging.getLogger(__name__)


def process_raw_jobs(
    db: Session,
    limit: int | None = None,
    generate_embeddings: bool = True,
    source: str | None = None,
    raw_job_ids: list[uuid.UUID] | None = None,
) -> dict:
    """Process all unprocessed raw_jobs into clean jobs.

    Args:
        db: Database session.
        limit: Max number of raw jobs to process (None = all).
        generate_embeddings: Whether to generate vector embeddings.
        source: Optional source filter (e.g. "adzuna").

    Returns:
        Summary dict with counts.
    """
    run = IngestionRun(
        id=uuid.uuid4(),
        source=source or "pipeline",
        started_at=datetime.utcnow(),
        status="running",
    )
    db.add(run)
    db.commit()

    query = db.query(RawJob).filter(RawJob.processed == False)  # noqa: E712
    if source:
        query = query.filter(RawJob.source == source)
    if raw_job_ids is not None:
        query = query.filter(RawJob.id.in_(raw_job_ids))
    if limit:
        query = query.limit(limit)

    raw_jobs = query.all()
    total = len(raw_jobs)

    if total == 0:
        run.finished_at = datetime.utcnow()
        run.status = "completed"
        db.commit()
        logger.info("No unprocessed raw jobs found.")
        return {"inserted": 0, "skipped": 0, "errors": 0, "quality_avg": 0.0}

    logger.info(f"Processing {total} raw jobs ...")
    inserted = 0
    skipped_dupes = 0
    errors = 0
    quality_scores: list[float] = []
    seen_hashes: set[str] = set()

    for i, raw in enumerate(raw_jobs, 1):
        try:
            raw.processing_attempts = (raw.processing_attempts or 0) + 1
            raw.ingestion_run_id = run.id
            job = _process_single(raw, generate_embeddings, db)

            if job is None:
                skipped_dupes += 1
                raw.processed = True
                db.commit()
                continue

            dedup_hash = job["dedup_hash"]

            original_job = db.query(Job).filter(Job.raw_job_id == raw.id).first()
            if original_job:
                quality = score_job(
                    title=job.get("title_clean"), company=job.get("company"),
                    description=job.get("description"), location_city=job.get("location_city"),
                    location_country=job.get("location_country"), salary_min=job.get("salary_min"),
                    salary_max=job.get("salary_max"), category=job.get("category"),
                    job_type=job.get("job_type"), experience_level=job.get("experience_level"),
                    skills=job.get("skills"), posted_at=job.get("posted_at"),
                    url=job.get("url"), source=raw.source,
                )
                collision = db.query(Job).filter(
                    Job.dedup_hash == dedup_hash, Job.id != original_job.id
                ).first()
                _update_existing_job(original_job, job, quality.overall, update_hash=not collision)
                original_job.skills.clear()
                for skill_name in job.get("skills", []):
                    original_job.skills.append(JobSkill(id=uuid.uuid4(), skill=skill_name))
                _upsert_posting(db, original_job, raw, job)
                raw.processed = True
                db.commit()
                quality_scores.append(quality.overall)
                inserted += 1
                continue

            if dedup_hash in seen_hashes:
                skipped_dupes += 1
                existing = db.query(Job).filter(Job.dedup_hash == dedup_hash).first()
                if existing:
                    _upsert_posting(db, existing, raw, job)
                raw.processed = True
                db.commit()
                continue

            existing = db.query(Job).filter(Job.dedup_hash == dedup_hash).first()
            if existing:
                skipped_dupes += 1
                seen_hashes.add(dedup_hash)
                _upsert_posting(db, existing, raw, job)
                raw.processed = True
                db.commit()
                continue

            seen_hashes.add(dedup_hash)

            # Score quality
            quality = score_job(
                title=job.get("title_clean"),
                company=job.get("company"),
                description=job.get("description"),
                location_city=job.get("location_city"),
                location_country=job.get("location_country"),
                salary_min=job.get("salary_min"),
                salary_max=job.get("salary_max"),
                category=job.get("category"),
                job_type=job.get("job_type"),
                experience_level=job.get("experience_level"),
                skills=job.get("skills"),
                posted_at=job.get("posted_at"),
                url=job.get("url"),
                source=raw.source,
            )
            quality_scores.append(quality.overall)

            new_job = Job(
                id=uuid.uuid4(),
                raw_job_id=raw.id,
                title=job["title"],
                title_clean=job["title_clean"],
                company=job["company"],
                description=job["description"],
                location_city=job["location_city"],
                location_country=job["location_country"],
                remote=job["remote"],
                uk_country=job.get("uk_country"),
                uk_region=job.get("uk_region"),
                county=job.get("county"),
                postcode_area=job.get("postcode_area"),
                workplace_type=job.get("workplace_type"),
                salary_min=job["salary_min"],
                salary_max=job["salary_max"],
                salary_currency=job["salary_currency"],
                salary_period=job["salary_period"],
                original_salary_text=job.get("original_salary_text"),
                annualised_gbp_salary=job.get("annualised_gbp_salary"),
                salary_confidence=job.get("salary_confidence"),
                category=job["category"],
                job_type=job.get("job_type"),
                experience_level=job.get("experience_level"),
                posted_at=job.get("posted_at"),
                url=job.get("url"),
                source=raw.source,
                dedup_hash=dedup_hash,
                embedding=job.get("embedding"),
                quality_score=quality.overall,
                processing_version="2.0",
            )
            db.add(new_job)
            db.flush()
            _upsert_posting(db, new_job, raw, job)

            for skill_name in job.get("skills", []):
                db.add(JobSkill(
                    id=uuid.uuid4(),
                    job_id=new_job.id,
                    skill=skill_name,
                ))

            raw.processed = True
            db.commit()
            inserted += 1

            if i % 50 == 0 or i == total:
                logger.info(f"  [{i}/{total}] — {inserted} inserted, {skipped_dupes} dupes")

        except Exception as e:
            db.rollback()
            errors += 1
            _log_processing_error(
                db=db,
                ingestion_run_id=run.id,
                raw_job_id=raw.id,
                source=raw.source,
                source_job_id=raw.source_job_id,
                error=e,
            )
            try:
                # Leave failed records retryable; the attempt and error are retained.
                raw.processed = False
                raw.processing_attempts = (raw.processing_attempts or 0) + 1
                db.commit()
            except Exception:
                db.rollback()
            continue

    # Finalise run
    run.finished_at = datetime.utcnow()
    run.records_fetched = total
    run.records_inserted = inserted
    run.records_skipped = skipped_dupes
    run.errors = errors
    run.status = "completed" if errors == 0 else "completed_with_errors"
    db.commit()

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    summary = {
        "inserted": inserted,
        "skipped": skipped_dupes,
        "errors": errors,
        "quality_avg": round(avg_quality, 1),
    }

    logger.info(
        f"Processing complete: {summary}"
    )
    return summary


def _process_single(raw: RawJob, generate_emb: bool, db: Session | None = None) -> dict | None:
    """Process a single raw job through all processors."""
    payload = raw.payload

    raw_title = payload.get("job_title", "")
    raw_description = payload.get("job_description", "")
    raw_company = payload.get("company", "")
    raw_category = payload.get("category", "")
    raw_skills = payload.get("skills", "")
    raw_location = payload.get("location_display", "")
    raw_url = payload.get("url", "")
    raw_posted = payload.get("posted_at", "")
    raw_salary_min = payload.get("salary_min")
    raw_salary_max = payload.get("salary_max")
    raw_salary_currency = payload.get("salary_currency")
    raw_contract_type = payload.get("contract_type")
    raw_contract_time = payload.get("contract_time")
    raw_experience_level = payload.get("experience_level")
    is_remote = payload.get("remote", False)

    if not raw_title and not raw_description:
        return None

    title_clean = clean_title(raw_title)

    salary = parse_salary(
        raw_description,
        source_min=raw_salary_min,
        source_max=raw_salary_max,
        source_currency=raw_salary_currency,
    )

    if db:
        raw_location = _resolve_alias(db, "location", raw_location)
        raw_category = _resolve_alias(db, "category", raw_category)
    location = normalise_location(raw_location, raw_description)
    if is_remote:
        location["remote"] = True

    category = normalise_category(raw_category, title_clean)

    skills = extract_skills(raw_description, raw_skills)

    job_type = _normalise_job_type(raw_contract_type, raw_contract_time)

    normalised_location_key = f"{location['city'] or ''} {location['country'] or ''}".strip()
    dedup_hash = generate_dedup_hash(
        title_clean, raw_company, normalised_location_key,
        salary.min_salary, salary.max_salary,
    )

    posted_at = _parse_date(raw_posted)

    embedding = None
    if generate_emb:
        text_for_embedding = build_job_text(title_clean, raw_description, skills)
        embedding = generate_embedding(text_for_embedding)

    return {
        "title": raw_title,
        "title_clean": title_clean,
        "company": raw_company or None,
        "description": raw_description or None,
        "location_city": location["city"],
        "location_country": location["country"],
        "remote": location["remote"],
        "uk_country": location.get("uk_country"),
        "uk_region": location.get("uk_region"),
        "county": location.get("county"),
        "postcode_area": location.get("postcode_area"),
        "workplace_type": location.get("workplace_type"),
        "salary_min": salary.min_salary,
        "salary_max": salary.max_salary,
        "salary_currency": salary.currency,
        "salary_period": salary.period,
        "original_salary_text": salary.original_text,
        "salary_confidence": salary.confidence,
        "annualised_gbp_salary": _annualised_salary(salary),
        "category": category,
        "job_type": job_type,
        "experience_level": raw_experience_level or None,
        "posted_at": posted_at,
        "url": raw_url or None,
        "dedup_hash": dedup_hash,
        "skills": skills,
        "embedding": embedding,
    }


def _normalise_job_type(contract_type: str | None, contract_time: str | None) -> str | None:
    """Normalise job type from various source formats."""
    text = f"{contract_type or ''} {contract_time or ''}".lower().strip()

    if not text:
        return None
    if "full" in text:
        return "full-time"
    if "part" in text:
        return "part-time"
    if "contract" in text or "freelance" in text:
        return "contract"
    if "intern" in text:
        return "internship"
    if "temporary" in text or "temp" in text:
        return "temporary"
    return None


def _parse_date(date_str: str | None) -> datetime | None:
    """Try to parse a date string from various formats."""
    if not date_str:
        return None

    from dateutil import parser as date_parser
    try:
        parsed = date_parser.parse(date_str)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except (ValueError, TypeError):
        return None


def _log_processing_error(
    db: Session,
    ingestion_run_id: uuid.UUID,
    raw_job_id: uuid.UUID,
    source: str,
    source_job_id: str,
    error: Exception,
):
    """Log a processing error to the processing_errors table."""
    error_type = type(error).__name__
    error_msg = str(error)[:2000]

    err = ProcessingError(
        id=uuid.uuid4(),
        ingestion_run_id=ingestion_run_id,
        raw_job_id=raw_job_id,
        error_type=error_type,
        error_message=error_msg,
        source=source,
        source_job_id=source_job_id,
        retry_count=0,
    )
    db.add(err)
    try:
        db.commit()
    except Exception:
        db.rollback()


def _resolve_alias(db: Session, kind: str, value: str | None) -> str | None:
    if not value:
        return value
    mapping = db.query(NormalizationAlias).filter(
        NormalizationAlias.kind == kind,
        NormalizationAlias.alias == value.strip().lower(),
        NormalizationAlias.is_active.is_(True),
    ).first()
    return mapping.canonical_value if mapping else value


def _annualised_salary(salary) -> float | None:
    from app.processing.salary import annualise_salary_gbp
    value = salary.min_salary if salary.min_salary is not None else salary.max_salary
    return annualise_salary_gbp(value, salary.currency, salary.period)


def _upsert_posting(db: Session, canonical_job: Job, raw: RawJob, processed: dict) -> None:
    posting = db.query(JobPosting).filter(JobPosting.raw_job_id == raw.id).first()
    if not posting:
        posting = JobPosting(id=uuid.uuid4(), raw_job_id=raw.id)
    posting.canonical_job_id = canonical_job.id
    posting.source = raw.source
    posting.source_job_id = raw.source_job_id
    posting.source_url = processed.get("url")
    posting.original_title = raw.payload.get("job_title")
    posting.original_description = raw.payload.get("job_description")
    posting.original_location = raw.payload.get("location_display")
    posting.original_salary_text = processed.get("original_salary_text")
    posting.original_currency = processed.get("salary_currency")
    posting.original_company = raw.payload.get("company")
    posting.payload = raw.payload
    posting.posted_at = processed.get("posted_at")
    posting.last_seen_at = datetime.utcnow()
    posting.is_active = True
    db.add(posting)


def _update_existing_job(job: Job, processed: dict, quality_score: float, update_hash: bool) -> None:
    fields = (
        "title", "title_clean", "company", "description", "location_city",
        "location_country", "remote", "uk_country", "uk_region", "county",
        "postcode_area", "workplace_type", "salary_min", "salary_max",
        "salary_currency", "salary_period", "original_salary_text",
        "annualised_gbp_salary", "salary_confidence", "category", "job_type",
        "experience_level", "posted_at", "url", "embedding",
    )
    for field in fields:
        setattr(job, field, processed.get(field))
    if update_hash:
        job.dedup_hash = processed["dedup_hash"]
    job.quality_score = quality_score
    job.processing_version = "2.0"
    job.updated_at = datetime.utcnow()
