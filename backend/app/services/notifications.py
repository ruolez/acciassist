"""Background notification tasks.

Each function opens its own DB session (request sessions are already closed
when FastAPI background tasks run) and delegates delivery to send_email,
which records the outcome and never raises.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import STAGE_LABELS, Case, IntakeSession, Lead, SummaryTemplate, User
from app.services import email as email_service
from app.services import email_templates
from app.services.email import base_url, get_app_settings, send_email

logger = logging.getLogger(__name__)


def format_estimate(minimum: int | None, maximum: int | None) -> str | None:
    if minimum is None or maximum is None:
        return None
    return f"${minimum:,} – ${maximum:,}"


async def _estimate_for_lead(db: AsyncSession, lead: Lead) -> str | None:
    if lead.intake_session_id is None:
        return None
    session = await db.get(IntakeSession, lead.intake_session_id)
    if session is None:
        return None
    tmpl = await db.scalar(
        select(SummaryTemplate).where(SummaryTemplate.injury_type_id == session.injury_type_id)
    )
    if tmpl is None:
        return None
    return format_estimate(tmpl.estimate_min, tmpl.estimate_max)


async def notify_lead_received(lead_id: int, raw_claim_token: str | None) -> None:
    factory = email_service.get_session_factory()
    async with factory() as db:
        case = await db.scalar(
            select(Case)
            .where(Case.lead_id == lead_id)
            .options(selectinload(Case.lead), selectinload(Case.user))
        )
        if case is None:
            logger.warning("notify_lead_received: no case for lead %s", lead_id)
            return
        app_settings = await get_app_settings(db)
        base = base_url(app_settings)
        estimate = await _estimate_for_lead(db, case.lead)
        if raw_claim_token:
            subject, html, text = email_templates.lead_received_claim(
                case.user.name, estimate, f"{base}/account/claim?token={raw_claim_token}"
            )
        else:
            subject, html, text = email_templates.lead_received_existing(
                case.user.name, estimate, f"{base}/login"
            )
        await send_email(
            db,
            to=case.user.email,
            subject=subject,
            html=html,
            text=text,
            purpose="lead_received",
            case_id=case.id,
        )


async def _notify_case(case_id: int, purpose: str) -> None:
    factory = email_service.get_session_factory()
    async with factory() as db:
        case = await db.scalar(
            select(Case).where(Case.id == case_id).options(selectinload(Case.user))
        )
        if case is None:
            logger.warning("%s: no case %s", purpose, case_id)
            return
        app_settings = await get_app_settings(db)
        case_url = f"{base_url(app_settings)}/account/cases/{case.id}"
        if purpose == "stage_changed":
            subject, html, text = email_templates.stage_changed(
                case.user.name, STAGE_LABELS[case.stage], case_url
            )
        else:
            subject, html, text = email_templates.case_update_posted(case.user.name, case_url)
        await send_email(
            db,
            to=case.user.email,
            subject=subject,
            html=html,
            text=text,
            purpose=purpose,
            case_id=case.id,
        )


async def notify_stage_changed(case_id: int) -> None:
    await _notify_case(case_id, "stage_changed")


async def notify_case_update(case_id: int) -> None:
    await _notify_case(case_id, "case_update")


async def send_password_reset(user_id: int, raw_token: str) -> None:
    factory = email_service.get_session_factory()
    async with factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            return
        app_settings = await get_app_settings(db)
        reset_url = f"{base_url(app_settings)}/reset-password?token={raw_token}"
        subject, html, text = email_templates.password_reset(user.name, reset_url)
        await send_email(
            db, to=user.email, subject=subject, html=html, text=text, purpose="password_reset"
        )
