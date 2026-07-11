"""SMTP delivery against the admin-configured settings row.

Sends are one-shot: the outcome lands in email_log (sent/failed/skipped) and
recovery is manual (resend invite / re-request link), so a lost email is
visible but never breaks the request that triggered it.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models import AppSettings, EmailLog, EmailStatus

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT_SECONDS = 15


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Background tasks open their own sessions through this indirection so
    tests can point it at the test database."""
    from app.db import SessionLocal

    return SessionLocal


async def get_app_settings(db: AsyncSession) -> AppSettings:
    row = await db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def smtp_configured(s: AppSettings) -> bool:
    return bool(s.smtp_host and s.from_email)


def base_url(s: AppSettings) -> str:
    url = s.app_base_url or (settings.cors_origin_list[0] if settings.cors_origin_list else "")
    return url.rstrip("/")


def _snapshot(s: AppSettings) -> dict:
    return {
        "host": s.smtp_host,
        "port": s.smtp_port,
        "username": s.smtp_username,
        "password": s.smtp_password,
        "tls_mode": s.smtp_tls_mode,
        "from_email": s.from_email,
        "from_name": s.from_name,
    }


def _send_via_smtp(snapshot: dict, msg: EmailMessage) -> None:
    """Blocking stdlib SMTP send; runs in a thread. Takes a plain dict so no
    ORM object crosses the thread boundary."""
    if snapshot["tls_mode"] == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            snapshot["host"], snapshot["port"], timeout=_SMTP_TIMEOUT_SECONDS
        )
    else:
        server = smtplib.SMTP(snapshot["host"], snapshot["port"], timeout=_SMTP_TIMEOUT_SECONDS)
    try:
        if snapshot["tls_mode"] == "starttls":
            server.starttls()
        if snapshot["username"]:
            server.login(snapshot["username"], snapshot["password"] or "")
        server.send_message(msg)
    finally:
        server.quit()


async def send_email(
    db: AsyncSession,
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
    purpose: str,
    case_id: int | None = None,
) -> EmailLog:
    """Send one email and record the outcome. Never raises."""
    app_settings = await get_app_settings(db)
    log = EmailLog(to_email=to, subject=subject, purpose=purpose, case_id=case_id)
    if not smtp_configured(app_settings):
        log.status = EmailStatus.skipped
        log.error = "SMTP is not configured"
    else:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{app_settings.from_name} <{app_settings.from_email}>"
        msg["To"] = to
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        try:
            await asyncio.to_thread(_send_via_smtp, _snapshot(app_settings), msg)
            log.status = EmailStatus.sent
        except Exception as exc:  # noqa: BLE001 — outcome is recorded, never raised
            logger.warning("email send to %s failed: %s", to, exc)
            log.status = EmailStatus.failed
            log.error = str(exc)[:2000]
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log
