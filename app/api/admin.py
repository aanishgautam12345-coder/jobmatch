"""Administrator-only monitoring and management API."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin
from app.database import get_db
from app.models.ingestion_run import IngestionRun
from app.models.job import Job
from app.models.normalization_alias import NormalizationAlias
from app.models.processing_error import ProcessingError
from app.models.user import User
from app.processing.category import CATEGORIES
from app.services.admin import (
    AdminValidationError,
    preview_normalization,
    reprocess_raw_jobs,
    sanitize_error,
    save_alias,
    update_job,
)

router = APIRouter()


class ReprocessRequest(BaseModel):
    confirmed: bool
    raw_job_id: uuid.UUID | None = None
    ingestion_run_id: uuid.UUID | None = None
    source: str | None = None
    failed_only: bool = False
    limit: int = Field(default=100, ge=1, le=500)


class JobUpdateRequest(BaseModel):
    title_clean: str | None = None
    company: str | None = None
    description: str | None = None
    description_clean: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None
    location_city: str | None = None
    location_country: str | None = None
    remote: bool | None = None
    category: str | None = None
    job_type: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    url: str | None = None


class AliasRequest(BaseModel):
    kind: str
    alias: str
    canonical_value: str
    is_active: bool = True


def _page(page: int, page_size: int) -> tuple[int, int]:
    return (page - 1) * page_size, page_size


@router.get("/ingestion-runs")
def ingestion_runs(
    source: str | None = None, status: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db), admin: User = Depends(get_current_admin),
):
    query = db.query(IngestionRun)
    if source:
        query = query.filter(IngestionRun.source == source)
    if status:
        query = query.filter(IngestionRun.status == status)
    total = query.count()
    offset, limit = _page(page, page_size)
    rows = query.order_by(IngestionRun.started_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [{
            "id": str(row.id), "source": row.source, "status": row.status,
            "started_at": row.started_at, "finished_at": row.finished_at,
            "records_fetched": row.records_fetched, "records_inserted": row.records_inserted,
            "records_skipped": row.records_skipped, "errors": row.errors,
            "error_message": sanitize_error(row.error_message),
        } for row in rows],
        "page": page, "page_size": page_size, "total": total,
    }


@router.get("/ingestion-runs/{run_id}")
def ingestion_run_detail(
    run_id: uuid.UUID, db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    run = db.get(IngestionRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    errors = db.query(ProcessingError).filter(ProcessingError.ingestion_run_id == run_id).all()
    return {
        "id": str(run.id), "source": run.source, "status": run.status,
        "started_at": run.started_at, "finished_at": run.finished_at,
        "records_fetched": run.records_fetched, "records_inserted": run.records_inserted,
        "records_skipped": run.records_skipped, "errors": run.errors,
        "error_message": sanitize_error(run.error_message),
        "processing_errors": [{
            "id": str(error.id), "raw_job_id": str(error.raw_job_id) if error.raw_job_id else None,
            "error_type": error.error_type, "message": sanitize_error(error.error_message),
            "created_at": error.created_at,
        } for error in errors],
    }


@router.post("/reprocess")
def reprocess(
    request: ReprocessRequest, db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if not request.confirmed:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required")
    try:
        return reprocess_raw_jobs(db, **request.model_dump(exclude={"confirmed"}))
    except AdminValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs")
def jobs(
    q: str | None = None, source: str | None = None, category: str | None = None,
    active: bool | None = None, page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    query = db.query(Job)
    if q:
        query = query.filter(or_(Job.title.ilike(f"%{q}%"), Job.company.ilike(f"%{q}%")))
    if source:
        query = query.filter(Job.source == source)
    if category:
        query = query.filter(Job.category == category)
    if active is not None:
        query = query.filter(Job.is_active.is_(active))
    total = query.count()
    offset, limit = _page(page, page_size)
    rows = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()
    return {"items": [_job_dict(job) for job in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/jobs/{job_id}")
def job_detail(job_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job, complete=True)


@router.put("/jobs/{job_id}")
def edit_job(
    job_id: uuid.UUID, request: JobUpdateRequest, db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        update_job(db, job, request.model_dump(exclude_unset=True))
    except AdminValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _job_dict(job, complete=True)


@router.post("/jobs/{job_id}/archive")
def archive_job(job_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return _set_active(db, job_id, False)


@router.post("/jobs/{job_id}/restore")
def restore_job(job_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return _set_active(db, job_id, True)


@router.get("/aliases")
def aliases(
    kind: str | None = None, db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    query = db.query(NormalizationAlias)
    if kind:
        query = query.filter(NormalizationAlias.kind == kind)
    return [{
        "id": str(row.id), "kind": row.kind, "alias": row.alias,
        "canonical_value": row.canonical_value, "is_active": row.is_active,
    } for row in query.order_by(NormalizationAlias.kind, NormalizationAlias.alias).all()]


@router.post("/aliases", status_code=201)
def create_alias(
    request: AliasRequest, db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    try:
        row = save_alias(db, **request.model_dump())
    except AdminValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": str(row.id)}


@router.put("/aliases/{alias_id}")
def edit_alias(
    alias_id: uuid.UUID, request: AliasRequest, db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    try:
        row = save_alias(db, alias_id=alias_id, **request.model_dump())
    except AdminValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": str(row.id), "is_active": row.is_active}


@router.get("/aliases/preview")
def preview_alias(
    kind: str, value: str, db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    try:
        return {"result": preview_normalization(db, kind, value)}
    except AdminValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _set_active(db: Session, job_id: uuid.UUID, active: bool):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.is_active = active
    job.updated_at = datetime.utcnow()
    db.commit()
    return {"id": str(job.id), "is_active": job.is_active}


def _job_dict(job: Job, complete: bool = False) -> dict:
    result = {
        "id": str(job.id), "title": job.title, "title_clean": job.title_clean,
        "company": job.company, "source": job.source, "category": job.category,
        "job_type": job.job_type, "is_active": job.is_active,
        "salary_min": job.salary_min, "salary_max": job.salary_max,
        "salary_currency": job.salary_currency, "salary_period": job.salary_period,
        "updated_at": job.updated_at,
    }
    if complete:
        result.update({
            "description": job.description, "location_city": job.location_city,
            "location_country": job.location_country, "remote": job.remote,
            "url": job.url, "original_salary_text": job.original_salary_text,
            "annualised_gbp_salary": job.annualised_gbp_salary,
        })
    return result
