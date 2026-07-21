from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DbSession
from app.errors import AppError
from app.models import AppSettings, EmailLog, EmailStatus
from app.schemas import EmailLogOut, SettingsIn, SettingsOut, TestEmailIn
from app.services import email_templates
from app.services.email import get_app_settings, send_email, smtp_configured

router = APIRouter()


def _to_out(row: AppSettings) -> SettingsOut:
    return SettingsOut(
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_username=row.smtp_username,
        smtp_password_set=bool(row.smtp_password),
        smtp_tls_mode=row.smtp_tls_mode,
        from_email=row.from_email,
        from_name=row.from_name,
        app_base_url=row.app_base_url,
        openrouter_api_key_set=bool(row.openrouter_api_key),
        openrouter_provisioning_key_set=bool(row.openrouter_provisioning_key),
        openrouter_model=row.openrouter_model,
        comps_enabled=row.comps_enabled,
        comps_model=row.comps_model,
        extraction_fallback_model=row.extraction_fallback_model,
        sample_count=row.sample_count,
        contingency_fee_pct=row.contingency_fee_pct,
    )


@router.get("", response_model=SettingsOut)
async def get_settings(db: DbSession) -> SettingsOut:
    return _to_out(await get_app_settings(db))


@router.put("", response_model=SettingsOut)
async def update_settings(data: SettingsIn, db: DbSession) -> SettingsOut:
    row = await get_app_settings(db)
    row.smtp_host = data.smtp_host
    row.smtp_port = data.smtp_port
    row.smtp_username = data.smtp_username
    if data.smtp_password is not None:
        row.smtp_password = data.smtp_password or None
    row.smtp_tls_mode = data.smtp_tls_mode
    row.from_email = data.from_email
    row.from_name = data.from_name
    row.app_base_url = data.app_base_url.rstrip("/") if data.app_base_url else None
    if data.openrouter_api_key is not None:
        row.openrouter_api_key = data.openrouter_api_key or None
    if data.openrouter_provisioning_key is not None:
        row.openrouter_provisioning_key = data.openrouter_provisioning_key or None
    row.openrouter_model = data.openrouter_model
    row.comps_enabled = data.comps_enabled
    row.comps_model = data.comps_model or None
    row.extraction_fallback_model = data.extraction_fallback_model or None
    row.sample_count = data.sample_count
    row.contingency_fee_pct = data.contingency_fee_pct
    await db.commit()
    await db.refresh(row)
    return _to_out(row)


@router.post("/test-email")
async def send_test_email(data: TestEmailIn, db: DbSession) -> dict[str, bool]:
    row = await get_app_settings(db)
    if not smtp_configured(row):
        raise AppError(400, "smtp_not_configured", "Configure SMTP host and from address first")
    subject, html, text = email_templates.test_email()
    log = await send_email(
        db, to=data.to_email, subject=subject, html=html, text=text, purpose="test"
    )
    if log.status != EmailStatus.sent:
        raise AppError(502, "smtp_send_failed", log.error or "SMTP send failed")
    return {"ok": True}


@router.get("/email-log", response_model=list[EmailLogOut])
async def email_log(db: DbSession) -> list[EmailLog]:
    rows = await db.scalars(select(EmailLog).order_by(EmailLog.created_at.desc()).limit(50))
    return list(rows)
