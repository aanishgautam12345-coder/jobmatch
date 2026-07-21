"""Jobs API — search and filtering endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.search import semantic_search, hybrid_search, keyword_search, find_similar_jobs, evidence_search

router = APIRouter()


@router.get("/search/semantic")
def search_semantic(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """AI-powered semantic search — ranks jobs by meaning, not keywords."""
    results = semantic_search(db, query=q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@router.get("/search/keyword")
def search_keyword(
    q: str = Query(..., description="Keyword search query"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Traditional keyword search — the baseline for comparison."""
    results = keyword_search(db, query=q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@router.get("/search/evidence")
def search_evidence(
    q: str = Query(..., description="Search query (short technical terms work best)"),
    limit: int = Query(20, ge=1, le=50),
    enable_fallback: bool = Query(True, description="Enable semantic fallback for few results"),
    db: Session = Depends(get_db),
):
    """Evidence-backed search — requires verifiable lexical evidence before returning results.

    For short technical queries (Azure, Python, Docker), returns only jobs with
    direct evidence in title, skills, requirements, or description. Falls back
    to semantic similarity only when insufficient evidence-backed results exist.
    """
    results = evidence_search(db, query=q, limit=limit, enable_semantic_fallback=enable_fallback)
    return {"query": q, "count": len(results), "results": results}


@router.get("/search/hybrid")
def search_hybrid(
    q: str = Query(..., description="Natural language search query"),
    country: str | None = Query(None, description="Filter by country"),
    remote_only: bool = Query(False),
    category: str | None = Query(None, description="Filter by canonical category"),
    min_salary: float | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Semantic search combined with structured filters."""
    results = hybrid_search(
        db, query=q, location_country=country, remote_only=remote_only,
        category=category, min_salary=min_salary, limit=limit,
    )
    return {"query": q, "count": len(results), "results": results}


@router.get("/{job_id}/similar")
def get_similar_jobs(
    job_id: str,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Find jobs similar to a given job — 'More like this'."""
    results = find_similar_jobs(db, job_id=job_id, limit=limit)
    return {"job_id": job_id, "count": len(results), "results": results}
