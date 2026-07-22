"""Email Service.

Sends notification digests using SMTP. Configured for Gmail's free tier
by default, but works with any SMTP provider.

If SMTP isn't configured (no credentials in .env), fails gracefully and
logs to console instead — the rest of the system keeps working.
"""

import logging
import smtplib
from html import escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import get_settings

logger = logging.getLogger(__name__)


def _send_message(message: MIMEMultipart) -> bool:
    settings = get_settings()
    if not settings.smtp_user or not settings.smtp_password:
        logger.info("SMTP is not configured; email was not sent")
        return False
    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        return True
    except Exception:
        logger.exception("SMTP delivery failed")
        return False


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """Send a password-reset message without logging its private URL."""
    settings = get_settings()
    safe_url = escape(reset_url, quote=True)
    message = MIMEMultipart("alternative")
    message["Subject"] = "Reset your JobMatch AI password"
    message["From"] = settings.email_from or settings.smtp_user
    message["To"] = to_email
    message.attach(MIMEText(
        "A password reset was requested for your JobMatch AI account. "
        f"Open this link to reset it: {reset_url}\n\n"
        "If you did not request this, you can ignore this email.",
        "plain",
    ))
    message.attach(MIMEText(
        "<p>A password reset was requested for your JobMatch AI account.</p>"
        f'<p><a href="{safe_url}">Reset your password</a></p>'
        "<p>If you did not request this, you can ignore this email.</p>",
        "html",
    ))
    return _send_message(message)


def send_notification_digest(
    to_email: str,
    user_name: str | None,
    jobs: list[dict],
) -> bool:
    """Send a job notification digest email."""
    settings = get_settings()

    subject = f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''} for you"
    body = _build_digest_html(user_name, jobs)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(
        "JobMatch AI found updates for you:\n\n" + "\n".join(
            f"{job.get('title', 'Job')} at {job.get('company') or 'Unknown company'} "
            f"({job.get('match_percentage', 0)}% match) {job.get('url') or ''}"
            for job in jobs
        ),
        "plain",
    ))
    msg.attach(MIMEText(body, "html"))

    try:
        delivered = _send_message(msg)
        if delivered:
            logger.info("Sent digest (%s jobs)", len(jobs))
        return delivered
    except Exception:
        logger.exception("Failed to build notification email")
        return False


def _build_digest_html(user_name: str | None, jobs: list[dict]) -> str:
    """Build a simple HTML email body for the digest."""
    greeting = f"Hi {escape(user_name)}," if user_name else "Hi,"

    job_rows = ""
    for job in jobs:
        title = escape(str(job.get("title") or "Job"))
        company = escape(str(job.get("company") or "N/A"))
        url = escape(str(job.get("url") or ""), quote=True)
        update_label = {
            "saved_job_update": "Related to a saved job",
            "recommendation_update": "New top recommendation",
        }.get(job.get("notification_type"), "New matching job")
        job_rows += f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">
                <small>{update_label}</small><br>
                <strong>{title}</strong><br>
                <span style="color: #666;">{company}</span><br>
                <span style="color: #2563eb; font-weight: bold;">{job['match_percentage']}% match</span>
                {f'<br><a href="{url}">View job</a>' if url else ''}
            </td>
        </tr>
        """

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2>{greeting}</h2>
        <p>We found {len(jobs)} new job{'s' if len(jobs) != 1 else ''} that match your profile:</p>
        <table style="width: 100%; border-collapse: collapse;">
            {job_rows}
        </table>
        <p style="color: #999; font-size: 12px; margin-top: 20px;">
            You're receiving this because you enabled job match notifications on JobMatch AI.
        </p>
    </body>
    </html>
    """
