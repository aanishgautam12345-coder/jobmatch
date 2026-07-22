"""Focused tests for administrator management and safe corrections."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.admin import ReprocessRequest, _set_active, reprocess
from app.core.deps import get_current_admin
from app.models.job import Job
from app.processing.pipeline import _resolve_alias
from app.processing.salary import annualise_salary_gbp
from app.services.admin import (
    AdminValidationError,
    MAX_REPROCESS_BATCH,
    reprocess_raw_jobs,
    sanitize_error,
    update_job,
)


class _Query:
    def __init__(self, result=None):
        self.result = result

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class _Db:
    def __init__(self, result=None):
        self.result = result
        self.commits = 0

    def query(self, model):
        return _Query(self.result)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def get(self, model, identifier):
        return self.result


def _job():
    return Job(
        id=uuid.uuid4(), title="Python Developer", title_clean="python developer",
        company="Acme", description="Build APIs", source="test", is_active=True,
        salary_min=40_000, salary_max=50_000, salary_currency="GBP",
        salary_period="annual",
    )


def test_normal_user_is_denied_admin_access():
    with pytest.raises(HTTPException) as exc:
        get_current_admin(SimpleNamespace(is_admin=False))
    assert exc.value.status_code == 403


def test_administrator_is_permitted():
    admin = SimpleNamespace(is_admin=True)
    assert get_current_admin(admin) is admin


def test_reprocessing_requires_confirmation():
    with pytest.raises(HTTPException) as exc:
        reprocess(ReprocessRequest(confirmed=False), _Db(), SimpleNamespace(is_admin=True))
    assert exc.value.status_code == 400


def test_reprocessing_batch_limit_is_bounded():
    with pytest.raises(AdminValidationError):
        reprocess_raw_jobs(_Db(), limit=MAX_REPROCESS_BATCH + 1)


@pytest.mark.parametrize("minimum,maximum", [(-1, 10), (20, -1), (100, 50)])
def test_job_edit_rejects_invalid_salary_ranges(minimum, maximum):
    with pytest.raises(AdminValidationError):
        update_job(_Db(), _job(), {"salary_min": minimum, "salary_max": maximum})


def test_semantic_job_edit_regenerates_embedding():
    job = _job()
    with patch("app.services.admin.generate_embedding", return_value=[0.1, 0.2]) as generate:
        update_job(_Db(), job, {"description": "Build secure APIs"})
    generate.assert_called_once()
    assert job.embedding == [0.1, 0.2]


def test_salary_only_edit_does_not_regenerate_embedding():
    job = _job()
    with patch("app.services.admin.generate_embedding") as generate:
        update_job(_Db(), job, {"salary_min": 45_000, "salary_max": 55_000})
    generate.assert_not_called()
    assert job.annualised_gbp_salary == 45_000


def test_archived_job_can_be_restored():
    job = _job()
    db = _Db(job)
    assert _set_active(db, job.id, False)["is_active"] is False
    assert _set_active(db, job.id, True)["is_active"] is True


@pytest.mark.parametrize(
    "kind,alias,canonical",
    [("category", "software dev", "Software Engineering"), ("location", "ldn", "London, United Kingdom")],
)
def test_persistent_alias_is_used_by_pipeline(kind, alias, canonical):
    mapping = SimpleNamespace(canonical_value=canonical)
    assert _resolve_alias(_Db(mapping), kind, alias) == canonical


def test_annual_salary_correction_uses_existing_normalization():
    assert annualise_salary_gbp(100, "GBP", "daily") == 26_000


def test_admin_error_summary_is_bounded_and_single_line():
    value = "failure\nTraceback: " + "x" * 1000
    safe = sanitize_error(value)
    assert "\n" not in safe
    assert len(safe) == 500
