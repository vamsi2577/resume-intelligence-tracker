"""
Minimal email sending.

When SMTP is configured (settings.SMTP_HOST set) a message is sent via SMTP.
Otherwise — dev / local / CI — the message is logged to the console so the
magic-link flow works with zero mail setup (copy the link from the logs).
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def send_email(*, to: str, subject: str, body: str) -> None:
    """Best-effort send. Never raises — a mail failure must not break the
    request flow (the caller already returns 200 to avoid leaking state)."""
    if not settings.SMTP_HOST:
        # No SMTP configured → log it. Magic links are short-lived; this is
        # only for local/dev where reading the console is acceptable.
        logger.info(
            "Email (SMTP not configured — logging instead)",
            extra={"to": to, "subject": subject, "body": body},
        )
        return

    try:
        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value())
            smtp.send_message(msg)
    except Exception:  # pragma: no cover - mail infra failure
        logger.error("Failed to send email", extra={"to": to}, exc_info=True)
