import uuid

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from app.deps import DbSession
from app.errors import AppError
from app.models import CaseEstimate, EstimateAdvice, InjuryType, IntakeSession, IntakeStatus
from app.schemas import CaseEstimateAdminOut, EstimateAdviceOut, OpenRouterModelOut
from app.services import openrouter
from app.services.email import get_app_settings
from app.services.estimates import generate_advice, schedule_estimate
from app.services.openrouter import OpenRouterError, ai_configured

router = APIRouter()


@router.get("/models", response_model=list[OpenRouterModelOut])
async def list_models(db: DbSession) -> list[dict]:
    row = await get_app_settings(db)
    if not row.openrouter_api_key:
        raise AppError(400, "ai_key_missing", "Save an OpenRouter API key first")
    try:
        return await openrouter.fetch_models(row.openrouter_api_key)
    except OpenRouterError as exc:
        raise AppError(502, exc.code, exc.message) from exc


@router.post("/test")
async def test_connection(db: DbSession) -> dict:
    row = await get_app_settings(db)
    if not ai_configured(row):
        raise AppError(400, "ai_not_configured", "Configure the OpenRouter key and model first")
    try:
        reply = await openrouter.chat_completion(
            row.openrouter_api_key,
            row.openrouter_model,
            [{"role": "user", "content": "Reply with the single word OK."}],
            referer=row.app_base_url,
        )
    except OpenRouterError as exc:
        raise AppError(502, exc.code, exc.message) from exc
    return {"ok": True, "model": row.openrouter_model, "reply": reply.strip()[:100]}


async def _injury_type_or_404(db: DbSession, injury_type_id: int) -> InjuryType:
    injury_type = await db.get(InjuryType, injury_type_id)
    if injury_type is None:
        raise AppError(404, "not_found", "Injury type not found")
    return injury_type


@router.get("/injury-types/{injury_type_id}/advice", response_model=EstimateAdviceOut | None)
async def get_advice(injury_type_id: int, db: DbSession) -> EstimateAdvice | None:
    await _injury_type_or_404(db, injury_type_id)
    return await db.scalar(
        select(EstimateAdvice).where(EstimateAdvice.injury_type_id == injury_type_id)
    )


@router.post("/injury-types/{injury_type_id}/advice", response_model=EstimateAdviceOut)
async def create_advice(injury_type_id: int, db: DbSession) -> EstimateAdvice:
    injury_type = await _injury_type_or_404(db, injury_type_id)
    return await generate_advice(db, injury_type)


async def _completed_session_or_error(db: DbSession, session_id: uuid.UUID) -> IntakeSession:
    session = await db.get(IntakeSession, session_id)
    if session is None:
        raise AppError(404, "not_found", "Intake session not found")
    if session.status != IntakeStatus.completed:
        raise AppError(409, "not_completed", "The questionnaire has not been completed yet")
    return session


@router.get("/sessions/{session_id}/estimate", response_model=CaseEstimateAdminOut | None)
async def get_estimate(session_id: uuid.UUID, db: DbSession) -> CaseEstimate | None:
    session = await db.get(IntakeSession, session_id)
    if session is None:
        raise AppError(404, "not_found", "Intake session not found")
    return await db.scalar(
        select(CaseEstimate).where(CaseEstimate.intake_session_id == session_id)
    )


@router.post("/sessions/{session_id}/estimate/rerun", response_model=CaseEstimateAdminOut)
async def rerun_estimate(
    session_id: uuid.UUID, db: DbSession, background_tasks: BackgroundTasks
) -> CaseEstimate:
    session = await _completed_session_or_error(db, session_id)
    if not ai_configured(await get_app_settings(db)):
        raise AppError(400, "ai_not_configured", "Configure the OpenRouter key and model first")
    estimate = await schedule_estimate(db, session, background_tasks)
    if estimate is None:
        raise AppError(400, "ai_not_configured", "Configure the OpenRouter key and model first")
    return estimate
