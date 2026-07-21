"""Email Service.

Sends notification digests using SMTP. Configured for Gmail's free tier
by default, but works with any SMTP provider.

If SMTP isn't configured (no credentials in .env), fails gracefully and
logs to console instead — the rest of the system keeps working.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_notification_digest(
    to_email: str,
    user_name: str | None,
    jobs: list[dict],
) -> bool:
    """Send a job notification digest email."""
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        logger.info(f"SMTP not configured — would send digest to {to_email} with {len(jobs)} jobs")
        return False

    subject = f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''} for you"
    body = _build_digest_html(user_name, jobs)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info(f"Sent digest to {to_email} ({len(jobs)} jobs)")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def _build_digest_html(user_name: str | None, jobs: list[dict]) -> str:
    """Build a simple HTML email body for the digest."""
    greeting = f"Hi {user_name}," if user_name else "Hi,"

    job_rows = ""
    for job in jobs:
        job_rows += f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">
                <strong>{job['title']}</strong><br>
                <span style="color: #666;">{job.get('company', 'N/A')}</span><br>
                <span style="color: #2563eb; font-weight: bold;">{job['match_percentage']}% match</span>
                {f'<br><a href="{job["url"]}">View job</a>' if job.get('url') else ''}
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
