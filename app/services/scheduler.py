"""APScheduler lifecycle for the dedicated notification worker."""

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.agents.notification_agent import NotificationAgent
from app.config import get_settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_scheduler: BackgroundScheduler | None = None


def _run_notification_cycle(frequency: str) -> None:
    db = SessionLocal()
    try:
        summary = NotificationAgent(db).run(frequency=frequency)
        logger.info("Scheduled notification cycle frequency=%s summary=%s", frequency, summary)
    except Exception:
        db.rollback()
        logger.exception("Scheduled notification cycle failed frequency=%s", frequency)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    """Start once in this process; callers must use the dedicated worker command."""
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Notification scheduler is disabled")
        return None
    with _lock:
        if _scheduler and _scheduler.running:
            return _scheduler
        scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
        scheduler.add_job(
            _run_notification_cycle,
            IntervalTrigger(minutes=settings.scheduler_instant_interval_minutes),
            args=["instant"], id="notifications-instant", replace_existing=True,
            max_instances=1, coalesce=True, misfire_grace_time=300,
        )
        daily_hour, daily_minute = _parse_time(settings.scheduler_daily_time)
        scheduler.add_job(
            _run_notification_cycle,
            CronTrigger(hour=daily_hour, minute=daily_minute, timezone=settings.scheduler_timezone),
            args=["daily"], id="notifications-daily", replace_existing=True,
            max_instances=1, coalesce=True, misfire_grace_time=3600,
        )
        weekly_hour, weekly_minute = _parse_time(settings.scheduler_weekly_time)
        scheduler.add_job(
            _run_notification_cycle,
            CronTrigger(
                day_of_week=settings.scheduler_weekly_day,
                hour=weekly_hour, minute=weekly_minute,
                timezone=settings.scheduler_timezone,
            ),
            args=["weekly"], id="notifications-weekly", replace_existing=True,
            max_instances=1, coalesce=True, misfire_grace_time=3600,
        )
        scheduler.start()
        _scheduler = scheduler
        logger.info("Notification scheduler started")
        return scheduler


def stop_scheduler() -> None:
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=True)
        _scheduler = None


def _parse_time(value: str) -> tuple[int, int]:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Scheduler times must use HH:MM") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Scheduler times must use HH:MM")
    return hour, minute
