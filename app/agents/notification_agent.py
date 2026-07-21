import logging
"""Notification Agent — the autonomous alerting layer.

Runs on a schedule (e.g. hourly/daily via APScheduler). For each active user:
    1. Find jobs added since the last run
    2. Score those jobs against the user's profile (reuses RecommendationAgent)
    3. DECIDE whether each job is worth notifying about:
         - meets the user's minimum match threshold?
         - not already notified for this job?
         - hasn't exceeded their notification rate cap?
    4. Send a single digest email (not one email per job — anti-spam)
    5. Log every notification sent

This is what makes it "agentic" rather than a blind alert-on-every-job system:
the agent actively filters for quality and prevents notification fatigue.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job, JobSkill
from app.models.user import User, UserProfile, NotificationPreference
from app.models.notification import Notification
from app.services.recommendation import compute_match_score


logger = logging.getLogger(__name__)

# Agent behaviour parameters
MAX_NOTIFICATIONS_PER_RUN = 5   # Anti-spam: cap per user per run, batch into a digest
DEFAULT_LOOKBACK_HOURS = 24     # How far back to consider "new" jobs on first run


class NotificationAgent:
    """Autonomous agent that decides which new jobs merit notifying users about."""

    def __init__(self, db: Session):
        self.db = db

    def run(self, since: datetime | None = None) -> dict:
        """Run one notification cycle across all active users.

        Args:
            since: Only consider jobs created after this time.
                   Defaults to DEFAULT_LOOKBACK_HOURS ago.

        Returns:
            Summary dict: {users_checked, notifications_sent, jobs_considered}
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=DEFAULT_LOOKBACK_HOURS)

        # Step 1 — find new jobs since last run
        new_jobs = self._get_new_jobs(since)
        logger.info(f"{len(new_jobs)} new jobs since {since}")

        if not new_jobs:
            return {"users_checked": 0, "notifications_sent": 0, "jobs_considered": 0}

        # Step 2 — get all users with active notification preferences
        users = self._get_active_users()
        logger.info(f"Checking {len(users)} active users")

        total_sent = 0

        for user in users:
            sent = self._process_user(user, new_jobs)
            # Also check the two additional notification types
            sent += self.check_saved_job_updates(user)
            sent += self.check_recommendation_updates(user)
            total_sent += sent

        return {
            "users_checked": len(users),
            "notifications_sent": total_sent,
            "jobs_considered": len(new_jobs),
        }

    def _get_new_jobs(self, since: datetime) -> list[Job]:
        stmt = select(Job).where(Job.created_at >= since).where(Job.embedding.isnot(None))
        return list(self.db.execute(stmt).scalars().all())

    def _get_active_users(self) -> list[User]:
        stmt = (
            select(User)
            .join(UserProfile, UserProfile.user_id == User.id)
            .join(NotificationPreference, NotificationPreference.user_id == User.id)
            .where(User.is_active.is_(True))
            .where(NotificationPreference.email_enabled.is_(True))
        )
        return list(self.db.execute(stmt).scalars().all())

    def _process_user(self, user: User, new_jobs: list[Job]) -> int:
        """Score new jobs for one user and decide what to notify about.

        Returns the number of notifications sent (0 or 1 — one digest email).
        """
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        prefs = self.db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user.id
        ).first()

        if not profile or not prefs:
            return 0

        # Ensure the profile has an embedding — don't silently skip users
        # who haven't triggered a recommendation run yet
        if profile.profile_embedding is None:
            from app.services.embedding import build_profile_text, generate_embedding
            text = build_profile_text(
                headline=profile.headline,
                skills=profile.skills,
                career_interests=profile.career_interests,
                experience_level=profile.experience_level,
            )
            profile.profile_embedding = generate_embedding(text)
            self.db.commit()
            logger.info(f"Computed missing profile embedding for {user.email}")

        # Score every new job against this user
        candidates = []
        for job in new_jobs:
            # Skip if already notified about this job
            already_notified = self.db.query(Notification).filter(
                Notification.user_id == user.id,
                Notification.job_id == job.id,
            ).first()
            if already_notified:
                continue

            similarity = self._cosine_similarity(profile.profile_embedding, job.embedding)
            job_skills = [s.skill for s in
                         self.db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]
            breakdown = compute_match_score(profile, job, job_skills, similarity)

            # DECISION: does this clear the user's personal threshold?
            if breakdown.overall_score >= prefs.min_match_score:
                candidates.append((job, breakdown))

        if not candidates:
            logger.info(f"No jobs cleared {user.email}'s "
                  f"{prefs.min_match_score*100:.0f}% threshold")
            return 0

        # Rank and cap — anti-spam: only the best N, batched into one digest
        candidates.sort(key=lambda c: c[1].overall_score, reverse=True)
        candidates = candidates[:MAX_NOTIFICATIONS_PER_RUN]

        # Determine notification type
        notif_type = "high_match" if candidates[0][1].overall_score >= 0.75 else "new_job"

        # Send the digest (or log it — email sending is wired separately)
        self._send_digest(user, profile, candidates, notif_type)

        return 1

    def _send_digest(self, user: User, profile: UserProfile,
                     candidates: list[tuple[Job, object]], notif_type: str):
        """Send one digest email covering all qualifying jobs, and log each."""
        import uuid
        from app.services.email import send_notification_digest

        job_summaries = [
            {
                "title": job.title_clean or job.title,
                "company": job.company,
                "match_percentage": breakdown.match_percentage,
                "url": job.url,
            }
            for job, breakdown in candidates
        ]

        # Attempt to send email (fails gracefully if SMTP isn't configured)
        send_notification_digest(user.email, profile.full_name, job_summaries)

        # Log every notification, regardless of email delivery success
        for job, breakdown in candidates:
            self.db.add(Notification(
                id=uuid.uuid4(),
                user_id=user.id,
                job_id=job.id,
                type=notif_type,
                match_score=breakdown.overall_score,
            ))

        self.db.commit()
        logger.info(f"Sent digest to {user.email}: "
              f"{len(candidates)} jobs (top match: {candidates[0][1].match_percentage}%)")

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        import numpy as np
        a = np.array(vec_a)
        b = np.array(vec_b)
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def check_saved_job_updates(self, user: User) -> int:
        """Saved Job Updates — notify if any saved job has been re-posted
        or a very similar job appears in the database.

        Checks each saved job for near-duplicates added recently.
        """
        from app.models.recommendation import SavedJob
        from app.services.search import find_similar_jobs
        import uuid

        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if not profile:
            return 0

        saved = self.db.query(SavedJob).filter(SavedJob.user_id == user.id).all()
        if not saved:
            return 0

        alerts = []
        for saved_job in saved:
            similar = find_similar_jobs(self.db, str(saved_job.job_id), limit=3)
            for s in similar:
                if s["similarity"] >= 0.85:
                    already = self.db.query(Notification).filter(
                        Notification.user_id == user.id,
                        Notification.job_id == s["id"],
                        Notification.type == "saved_job_update",
                    ).first()
                    if not already:
                        alerts.append(s)

        if not alerts:
            return 0

        for alert in alerts[:MAX_NOTIFICATIONS_PER_RUN]:
            self.db.add(Notification(
                id=uuid.uuid4(),
                user_id=user.id,
                job_id=uuid.UUID(alert["id"]),
                type="saved_job_update",
                match_score=alert["similarity"],
            ))

        self.db.commit()
        logger.info(f"{len(alerts[:MAX_NOTIFICATIONS_PER_RUN])} saved job update(s) for {user.email}")
        return 1

    def check_recommendation_updates(self, user: User) -> int:
        """Recommendation Updates — notify if the user's top recommendation
        has changed since the last notification cycle.

        Compares current top-1 recommendation against the last stored one.
        """
        from app.models.recommendation import Recommendation
        from app.agents.recommendation_agent import RecommendationAgent
        import uuid

        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if not profile or profile.profile_embedding is None:
            return 0

        # Get current top recommendation
        agent = RecommendationAgent(self.db)
        current_recs = agent.recommend(profile, top_n=1)
        if not current_recs:
            return 0

        current_top_id = current_recs[0]["job_id"]

        # Check if we already notified about this specific top recommendation
        already = self.db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.job_id == current_top_id,
            Notification.type == "recommendation_update",
        ).first()

        if already:
            return 0  # Same top rec as before, no update needed

        self.db.add(Notification(
            id=uuid.uuid4(),
            user_id=user.id,
            job_id=uuid.UUID(current_top_id),
            type="recommendation_update",
            match_score=current_recs[0]["match_percentage"] / 100,
        ))
        self.db.commit()
        logger.info(f"New top recommendation for {user.email}: "
              f"{current_recs[0]['title']} ({current_recs[0]['match_percentage']}%)")
        return 1
