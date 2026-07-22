"""Frequency-aware, idempotent email notification agent."""

import logging
import uuid
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.job import Job, JobSkill
from app.models.notification import Notification
from app.models.recommendation import Recommendation, SavedJob
from app.models.user import NotificationPreference, User, UserProfile
from app.services.email import send_notification_digest
from app.services.recommendation import compute_match_score
from app.services.search import find_similar_jobs

logger = logging.getLogger(__name__)
DEFAULT_LOOKBACK_HOURS = 24


class NotificationAgent:
    """Select and deliver due notifications without recording false success."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def run(self, since: datetime | None = None, frequency: str | None = None) -> dict:
        if frequency is not None and frequency not in {"instant", "daily", "weekly"}:
            raise ValueError("Unsupported notification frequency")
        default_hours = 24 * 7 if frequency == "weekly" else DEFAULT_LOOKBACK_HOURS
        since = since or datetime.utcnow() - timedelta(hours=default_hours)
        new_jobs = self._get_new_jobs(since)
        users = self._get_active_users(frequency)
        emails_sent = 0
        emails_failed = 0
        notifications_sent = 0

        for user in users:
            result = self._process_user(user, new_jobs)
            emails_sent += int(result["delivered"])
            emails_failed += int(result["attempted"] and not result["delivered"])
            notifications_sent += result["notifications_sent"]

        summary = {
            "users_checked": len(users),
            "jobs_considered": len(new_jobs),
            "emails_sent": emails_sent,
            "emails_failed": emails_failed,
            "notifications_sent": notifications_sent,
        }
        logger.info("Notification run complete frequency=%s summary=%s", frequency or "all", summary)
        return summary

    def _get_new_jobs(self, since: datetime) -> list[Job]:
        stmt = select(Job).where(
            Job.created_at >= since,
            Job.embedding.isnot(None),
            Job.is_active.is_(True),
        )
        return list(self.db.execute(stmt).scalars().all())

    def _get_active_users(self, frequency: str | None) -> list[User]:
        stmt = (
            select(User)
            .join(UserProfile, UserProfile.user_id == User.id)
            .join(NotificationPreference, NotificationPreference.user_id == User.id)
            .where(User.is_active.is_(True), NotificationPreference.email_enabled.is_(True))
        )
        if frequency:
            stmt = stmt.where(NotificationPreference.frequency == frequency)
        return list(self.db.execute(stmt).scalars().all())

    def _process_user(self, user: User, new_jobs: list[Job]) -> dict:
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        prefs = self.db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user.id
        ).first()
        if not profile or not prefs or not prefs.email_enabled:
            return {"attempted": False, "delivered": False, "notifications_sent": 0}

        if profile.profile_embedding is None:
            from app.services.embedding import build_profile_text, generate_embedding
            profile.profile_embedding = generate_embedding(build_profile_text(
                headline=profile.headline, skills=profile.skills,
                career_interests=profile.career_interests,
                experience_level=profile.experience_level,
            ), is_query=True)
            self.db.commit()

        if prefs.last_processed_at:
            new_jobs = [job for job in new_jobs if job.created_at >= prefs.last_processed_at]

        candidates = self._new_job_candidates(user, profile, prefs, new_jobs)
        candidates.extend(self._saved_job_candidates(user))
        recommendation = self._recommendation_candidate(user)
        if recommendation:
            candidates.append(recommendation)

        candidates.sort(key=lambda item: item[1], reverse=True)
        prefs.last_processed_at = datetime.utcnow()
        if not candidates:
            self.db.commit()
            return {"attempted": False, "delivered": False, "notifications_sent": 0}
        return self._deliver(user, profile, prefs, candidates)

    def _new_job_candidates(self, user, profile, prefs, jobs):
        candidates = []
        for job in jobs:
            similarity = self._cosine_similarity(profile.profile_embedding, job.embedding)
            skills = [row.skill for row in self.db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]
            breakdown = compute_match_score(
                profile, job, skills, similarity, profile.preferred_job_types,
            )
            if breakdown.overall_score >= prefs.min_match_score:
                notification_type = "high_match" if breakdown.overall_score >= 0.75 else "new_job"
                candidates.append((job, breakdown.overall_score, notification_type))
        return candidates

    def _saved_job_candidates(self, user):
        candidates = {}
        for saved in self.db.query(SavedJob).filter(SavedJob.user_id == user.id).all():
            for result in find_similar_jobs(self.db, str(saved.job_id), limit=3):
                if result["similarity"] < 0.85:
                    continue
                job = self.db.query(Job).filter(
                    Job.id == uuid.UUID(result["id"]), Job.is_active.is_(True)
                ).first()
                if job:
                    candidates[job.id] = (job, result["similarity"], "saved_job_update")
        return list(candidates.values())

    def _recommendation_candidate(self, user):
        current = (
            self.db.query(Recommendation)
            .join(Job, Job.id == Recommendation.job_id)
            .filter(Recommendation.user_id == user.id, Job.is_active.is_(True))
            .order_by(Recommendation.created_at.desc(), Recommendation.rank.asc())
            .first()
        )
        if not current:
            return None
        previous = (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user.id,
                Notification.type == "recommendation_update",
                Notification.status == "sent",
            )
            .order_by(Notification.sent_at.desc())
            .first()
        )
        if previous and previous.job_id == current.job_id:
            return None
        job = self.db.query(Job).filter(Job.id == current.job_id, Job.is_active.is_(True)).first()
        transition = str(previous.job_id) if previous else "initial"
        return (job, current.match_score, f"recommendation_update:{transition}") if job else None

    def _deliver(self, user, profile, prefs, candidates):
        digest_id = uuid.uuid4()
        reserved = []
        max_retries = self.settings.notification_max_retries
        for job, score, notification_type in candidates:
            if len(reserved) >= self.settings.notification_digest_limit:
                break
            base_type, _, _ = notification_type.partition(":")
            dedupe_key = f"{user.id}:{job.id}:{notification_type}"
            notification = self.db.query(Notification).filter(
                Notification.dedupe_key == dedupe_key
            ).first()
            if notification and (notification.status == "sent" or notification.retry_count >= max_retries):
                continue
            if (
                notification and notification.status == "pending"
                and notification.attempted_at
                and notification.attempted_at >= datetime.utcnow() - timedelta(minutes=30)
            ):
                continue
            if not notification:
                notification = Notification(
                    id=uuid.uuid4(), user_id=user.id, job_id=job.id,
                    type=base_type, match_score=score,
                    dedupe_key=dedupe_key, status="pending", retry_count=0,
                )
            notification.digest_id = digest_id
            notification.status = "pending"
            notification.attempted_at = datetime.utcnow()
            notification.retry_count = (notification.retry_count or 0) + 1
            self.db.add(notification)
            reserved.append((notification, job, score, base_type))
        self.db.commit()
        if not reserved:
            return {"attempted": False, "delivered": False, "notifications_sent": 0}

        summaries = [{
            "title": job.title_clean or job.title,
            "company": job.company,
            "match_percentage": round(score * 100, 1),
            "url": job.url,
            "notification_type": notification_type,
        } for _, job, score, notification_type in reserved]
        delivered = send_notification_digest(user.email, profile.full_name, summaries)
        now = datetime.utcnow()
        for notification, _, _, _ in reserved:
            notification.status = "sent" if delivered else "failed"
            notification.sent_at = now if delivered else None
            notification.failure_reason = None if delivered else "Email delivery failed"
        if delivered:
            prefs.last_digest_sent_at = now
        self.db.commit()
        return {
            "attempted": True, "delivered": delivered,
            "notifications_sent": len(reserved) if delivered else 0,
        }

    @staticmethod
    def _cosine_similarity(vec_a, vec_b) -> float:
        a = np.array(vec_a)
        b = np.array(vec_b)
        denominator = np.linalg.norm(a) * np.linalg.norm(b)
        if denominator == 0:
            return 0.0
        return max(0.0, min(1.0, float(np.dot(a, b) / denominator)))

    # Public compatibility helpers used by existing scripts.
    def check_saved_job_updates(self, user: User) -> int:
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        prefs = self.db.query(NotificationPreference).filter(NotificationPreference.user_id == user.id).first()
        candidates = self._saved_job_candidates(user)
        if not profile or not prefs or not candidates:
            return 0
        return int(self._deliver(user, profile, prefs, candidates)["delivered"])

    def check_recommendation_updates(self, user: User) -> int:
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        prefs = self.db.query(NotificationPreference).filter(NotificationPreference.user_id == user.id).first()
        candidate = self._recommendation_candidate(user)
        if not profile or not prefs or not candidate:
            return 0
        return int(self._deliver(user, profile, prefs, [candidate])["delivered"])
