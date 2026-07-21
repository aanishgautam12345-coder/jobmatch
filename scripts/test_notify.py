"""Test the Notification Agent.

Ensures the demo user has notification preferences, then runs one
notification cycle and reports what was sent.

Usage:
    python -m scripts.test_notify
"""

import sys
import os
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import *  # noqa: F401,F403
from app.models.user import NotificationPreference
from app.agents.notification_agent import NotificationAgent
from scripts.test_recommend import get_or_create_demo_profile


def ensure_notification_prefs(db, user_id, min_match_score: float = 0.5):
    """Create notification preferences for the demo user if missing."""
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id
    ).first()

    if not prefs:
        prefs = NotificationPreference(
            id=uuid.uuid4(),
            user_id=user_id,
            email_enabled=True,
            min_match_score=min_match_score,
            frequency="daily",
        )
        db.add(prefs)
        db.commit()
        print(f"  Created notification preferences (min match: {min_match_score*100}%)")
    else:
        prefs.min_match_score = min_match_score
        db.commit()
        print(f"  Updated notification preferences (min match: {min_match_score*100}%)")

    return prefs


def main():
    db = SessionLocal()
    try:
        print("\n" + "="*75)
        print("  JobMatch AI — Notification Agent Demo")
        print("="*75)

        profile = get_or_create_demo_profile(db)
        ensure_notification_prefs(db, profile.user_id, min_match_score=0.5)

        # Look back further than the default since our demo data was seeded
        # all at once (in a real deployment, jobs trickle in continuously)
        since = datetime.utcnow() - timedelta(days=365)

        print(f"\nRunning notification cycle (looking back to {since.date()}) ...\n")

        agent = NotificationAgent(db)
        summary = agent.run(since=since)

        print(f"\n{'='*75}")
        print(f"  SUMMARY")
        print(f"{'='*75}")
        print(f"  Users checked:        {summary['users_checked']}")
        print(f"  Jobs considered:      {summary['jobs_considered']}")
        print(f"  Notifications sent:   {summary['notifications_sent']}")
        print(f"\n  Note: without SMTP configured in .env, emails are logged")
        print(f"  to console instead of actually sent — this still proves")
        print(f"  the decision logic (who gets notified, what jobs, why).")

    finally:
        db.close()


if __name__ == "__main__":
    main()
