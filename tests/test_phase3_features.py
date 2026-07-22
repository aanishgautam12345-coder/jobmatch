"""Focused tests for scheduler, delivery truthfulness, and personalized search."""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.agents.notification_agent import NotificationAgent
from app.api.jobs import search_hybrid
from app.models.job import Job
from app.models.notification import Notification
from app.models.recommendation import Recommendation
from app.models.user import NotificationPreference, UserProfile
from app.services.search import personalized_search


class _Query:
    def __init__(self, result=None, rows=None):
        self.result = result
        self.rows = rows or []

    def filter(self, *args):
        return self

    def join(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.rows


class _DeliveryDb:
    def __init__(self):
        self.notifications = []
        self.commits = 0

    def query(self, model):
        if model is Notification:
            return _Query(self.notifications[-1] if self.notifications else None)
        return _Query(rows=[])

    def add(self, value):
        if isinstance(value, Notification) and value not in self.notifications:
            self.notifications.append(value)

    def commit(self):
        self.commits += 1


def _delivery_parts():
    user = SimpleNamespace(id=uuid.uuid4(), email="person@example.com")
    profile = SimpleNamespace(full_name="Person")
    prefs = SimpleNamespace(last_digest_sent_at=None)
    job = SimpleNamespace(
        id=uuid.uuid4(), title="Developer", title_clean="Python Developer",
        company="Acme", url="https://example.test/job",
    )
    return user, profile, prefs, job


def test_scheduler_does_not_start_during_import_or_when_disabled():
    import app.services.scheduler as scheduler
    scheduler._scheduler = None
    with patch("app.services.scheduler.get_settings", return_value=SimpleNamespace(scheduler_enabled=False)):
        assert scheduler.start_scheduler() is None
    assert scheduler._scheduler is None


def test_duplicate_scheduler_start_is_prevented():
    import app.services.scheduler as scheduler
    existing = SimpleNamespace(running=True)
    scheduler._scheduler = existing
    with patch("app.services.scheduler.get_settings", return_value=SimpleNamespace(scheduler_enabled=True)):
        assert scheduler.start_scheduler() is existing
    scheduler._scheduler = None


@pytest.mark.parametrize("frequency", ["instant", "daily", "weekly"])
def test_notification_run_selects_requested_frequency(frequency):
    agent = NotificationAgent(MagicMock())
    agent._get_new_jobs = MagicMock(return_value=[])
    agent._get_active_users = MagicMock(return_value=[])
    agent.run(frequency=frequency)
    agent._get_active_users.assert_called_once_with(frequency)


def test_smtp_success_marks_notifications_sent():
    db = _DeliveryDb()
    agent = NotificationAgent(db)
    user, profile, prefs, job = _delivery_parts()
    with patch("app.agents.notification_agent.send_notification_digest", return_value=True):
        result = agent._deliver(user, profile, prefs, [(job, 0.9, "new_job")])
    assert result["notifications_sent"] == 1
    assert db.notifications[0].status == "sent"
    assert db.notifications[0].sent_at is not None


def test_smtp_failure_does_not_mark_notification_sent():
    db = _DeliveryDb()
    agent = NotificationAgent(db)
    user, profile, prefs, job = _delivery_parts()
    with patch("app.agents.notification_agent.send_notification_digest", return_value=False):
        result = agent._deliver(user, profile, prefs, [(job, 0.9, "new_job")])
    assert result["notifications_sent"] == 0
    assert db.notifications[0].status == "failed"
    assert db.notifications[0].sent_at is None


def test_successful_delivery_is_idempotent():
    db = _DeliveryDb()
    agent = NotificationAgent(db)
    user, profile, prefs, job = _delivery_parts()
    with patch("app.agents.notification_agent.send_notification_digest", return_value=True) as sender:
        agent._deliver(user, profile, prefs, [(job, 0.9, "new_job")])
        second = agent._deliver(user, profile, prefs, [(job, 0.9, "new_job")])
    assert second["attempted"] is False
    sender.assert_called_once()


def test_retry_is_bounded():
    db = _DeliveryDb()
    agent = NotificationAgent(db)
    user, profile, prefs, job = _delivery_parts()
    db.notifications.append(Notification(
        id=uuid.uuid4(), user_id=user.id, job_id=job.id, type="new_job",
        match_score=0.9, status="failed",
        retry_count=agent.settings.notification_max_retries,
        dedupe_key=f"{user.id}:{job.id}:new_job",
    ))
    with patch("app.agents.notification_agent.send_notification_digest") as sender:
        result = agent._deliver(user, profile, prefs, [(job, 0.9, "new_job")])
    assert result["attempted"] is False
    sender.assert_not_called()


def test_recent_pending_delivery_prevents_concurrent_duplicate():
    db = _DeliveryDb()
    agent = NotificationAgent(db)
    user, profile, prefs, job = _delivery_parts()
    db.notifications.append(Notification(
        id=uuid.uuid4(), user_id=user.id, job_id=job.id, type="new_job",
        match_score=0.9, status="pending", attempted_at=datetime.utcnow(),
        retry_count=1, dedupe_key=f"{user.id}:{job.id}:new_job",
    ))
    with patch("app.agents.notification_agent.send_notification_digest") as sender:
        result = agent._deliver(user, profile, prefs, [(job, 0.9, "new_job")])
    assert result["attempted"] is False
    sender.assert_not_called()


@pytest.mark.parametrize("notification_type", ["saved_job_update", "recommendation_update"])
def test_update_notification_produces_email(notification_type):
    db = _DeliveryDb()
    agent = NotificationAgent(db)
    user, profile, prefs, job = _delivery_parts()
    with patch("app.agents.notification_agent.send_notification_digest", return_value=True) as sender:
        agent._deliver(user, profile, prefs, [(job, 0.88, notification_type)])
    sender.assert_called_once()
    assert db.notifications[0].type == notification_type
    assert db.notifications[0].status == "sent"


def test_disabled_notifications_send_nothing():
    profile = SimpleNamespace(profile_embedding=[1.0], skills=["python"], headline="Developer")
    prefs = SimpleNamespace(email_enabled=False)

    class Db:
        def query(self, model):
            return _Query(profile if model is UserProfile else prefs)

    agent = NotificationAgent(Db())
    with patch.object(agent, "_deliver") as deliver:
        result = agent._process_user(SimpleNamespace(id=uuid.uuid4()), [])
    assert result["attempted"] is False
    deliver.assert_not_called()


def test_below_threshold_job_is_not_selected():
    job = SimpleNamespace(id=uuid.uuid4(), embedding=[1.0])
    profile = SimpleNamespace(profile_embedding=[1.0], preferred_job_types=[])
    prefs = SimpleNamespace(min_match_score=0.8)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    agent = NotificationAgent(db)
    with patch(
        "app.agents.notification_agent.compute_match_score",
        return_value=SimpleNamespace(overall_score=0.79),
    ):
        assert agent._new_job_candidates(SimpleNamespace(), profile, prefs, [job]) == []


def test_digest_limit_is_enforced_before_delivery():
    class LimitDb(_DeliveryDb):
        def query(self, model):
            return _Query(None) if model is Notification else _Query(rows=[])

    db = LimitDb()
    agent = NotificationAgent(db)
    user, profile, prefs, _ = _delivery_parts()
    candidates = [(_delivery_parts()[3], score / 10, "new_job") for score in range(10)]
    with patch("app.agents.notification_agent.send_notification_digest", return_value=True):
        agent._deliver(user, profile, prefs, candidates)
    assert len(db.notifications) == agent.settings.notification_digest_limit


def test_unchanged_top_recommendation_produces_no_candidate():
    job_id = uuid.uuid4()
    current = SimpleNamespace(job_id=job_id, match_score=0.9)
    previous = SimpleNamespace(job_id=job_id)

    class Db:
        def query(self, model):
            if model is Recommendation:
                return _Query(current)
            if model is Notification:
                return _Query(previous)
            return _Query()

    assert NotificationAgent(Db())._recommendation_candidate(SimpleNamespace(id=uuid.uuid4())) is None


def test_recommended_api_requires_authentication():
    with pytest.raises(HTTPException) as exc:
        search_hybrid(
            q="python", country=None, remote_only=False, category=None,
            min_salary=None, limit=10, recommended=True, user=None, db=MagicMock(),
        )
    assert exc.value.status_code == 401


def test_recommended_api_rejects_incomplete_profile():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        profile_embedding=None, skills=[], headline=None,
    )
    with pytest.raises(HTTPException) as exc:
        search_hybrid(
            q="python", country=None, remote_only=False, category=None,
            min_salary=None, limit=10, recommended=True,
            user=SimpleNamespace(id=uuid.uuid4()), db=db,
        )
    assert exc.value.status_code == 422


def test_personalized_search_changes_ranking_and_returns_match_percentage():
    first = Job(id=uuid.uuid4(), title="Python", source="test", is_active=True, description="python")
    second = Job(id=uuid.uuid4(), title="Developer", source="test", is_active=True, description="python developer")
    jobs = {str(first.id): first, str(second.id): second}

    class SearchDb:
        def query(self, model):
            query = _Query()
            query.filter = lambda *args: query
            query.first = lambda: next(iter(jobs.values()))
            if model.__name__ == "JobSkill":
                query.all = lambda: []
            return query

    candidates = [
        {"id": str(first.id), "similarity": 0.9, "ranking_score": 90, "title": "Python"},
        {"id": str(second.id), "similarity": 0.7, "ranking_score": 70, "title": "Developer"},
    ]
    scores = iter([0.4, 0.9])
    profile = SimpleNamespace(preferred_job_types=[])
    with patch("app.services.search.hybrid_search", return_value=candidates), patch(
        "app.services.recommendation.compute_match_score",
        side_effect=lambda *args, **kwargs: SimpleNamespace(overall_score=next(scores)),
    ):
        results = personalized_search(SearchDb(), "python", profile, threshold=0.3)
    assert results[0]["profile_match_score"] == 90.0
    assert results[0]["match_percentage"] == 90.0
