import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from app.deps import DbSession
from app.errors import AppError
from app.models import (
    CaseEstimate,
    EstimateAdvice,
    EstimateStatus,
    InjuryType,
    IntakeSession,
    IntakeStatus,
)
from app.schemas import (
    AdviceApplyIn,
    CaseEstimateAdminOut,
    EstimateAdviceOut,
    OpenRouterModelOut,
    QuestionIn,
)
from app.services import openrouter
from app.services.email import get_app_settings
from app.services.estimates import generate_advice, schedule_estimate
from app.services.openrouter import OpenRouterError, ai_configured
from app.services.questions import apply_question_update, create_questions, load_question

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


@router.post(
    "/injury-types/{injury_type_id}/advice/apply", response_model=EstimateAdviceOut
)
async def apply_advice(
    injury_type_id: int, data: AdviceApplyIn, db: DbSession
) -> EstimateAdvice:
    """Apply selected stored proposals in one transaction: create proposed
    questions and update edit targets exactly as the builder endpoints would.
    The stored row is the source of truth — the client only sends ids."""
    await _injury_type_or_404(db, injury_type_id)
    advice = await db.scalar(
        select(EstimateAdvice).where(EstimateAdvice.injury_type_id == injury_type_id)
    )
    if advice is None or not advice.proposals:
        raise AppError(404, "no_advice", "Generate AI recommendations first")
    by_id = {p["id"]: p for p in advice.proposals}
    unknown = [pid for pid in data.proposal_ids if pid not in by_id]
    if unknown:
        raise AppError(400, "invalid_proposal", f"Unknown proposal id: {unknown[0]}")

    requested = set(data.proposal_ids)
    # Stored-list order keeps created display_order deterministic regardless of
    # the order checkboxes were ticked; already-applied ids are skipped so
    # re-applying is idempotent.
    selected = [p for p in advice.proposals if p["id"] in requested and not p["applied"]]

    add_drafts: list[tuple[dict, QuestionIn]] = []
    for proposal in selected:
        payload = QuestionIn.model_validate(proposal["payload"])
        if proposal["kind"] == "add":
            add_drafts.append((proposal, payload))
        else:
            try:
                question = await load_question(db, injury_type_id, proposal["question_id"])
            except AppError as exc:
                raise AppError(
                    409,
                    "stale_proposal",
                    f"The question targeted by proposal {proposal['id']} no longer exists",
                ) from exc
            apply_question_update(question, payload)

    created = await create_questions(db, injury_type_id, [d for _, d in add_drafts])
    await db.flush()

    applied_at = datetime.now(UTC).isoformat()
    created_ids = {p["id"]: q.id for (p, _), q in zip(add_drafts, created, strict=True)}
    applied_ids = {p["id"] for p in selected}
    new_proposals = []
    for proposal in advice.proposals:
        item = dict(proposal)
        if item["id"] in applied_ids:
            item["applied"] = True
            item["applied_at"] = applied_at
            if item["kind"] == "add":
                item["created_question_id"] = created_ids[item["id"]]
        new_proposals.append(item)
    # Reassignment (not mutation) so SQLAlchemy detects the JSONB change.
    advice.proposals = new_proposals
    await db.commit()
    await db.refresh(advice)
    return advice


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


def _estimate_gaps(estimate: CaseEstimate) -> list[str]:
    """Missing facts from the latest run: the assembled improvements list plus
    the extraction's missing driver fields, deduped in order."""
    extraction = (estimate.internals or {}).get("extraction") or {}
    driver_fields = (extraction.get("extraction_notes") or {}).get("missing_driver_fields") or []
    gaps: list[str] = []
    seen: set[str] = set()
    for item in [*(estimate.missing_info or []), *driver_fields]:
        text = str(item).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            gaps.append(text)
    return gaps


@router.post(
    "/sessions/{session_id}/estimate/propose-questions", response_model=EstimateAdviceOut
)
async def propose_gap_questions(session_id: uuid.UUID, db: DbSession) -> EstimateAdvice:
    """Turn the latest estimate's missing information into questionnaire
    proposals via the standard advice system (reviewed/applied like any other
    advice). New questions help future intakes only."""
    session = await _completed_session_or_error(db, session_id)
    estimate = await db.scalar(
        select(CaseEstimate).where(CaseEstimate.intake_session_id == session_id)
    )
    if estimate is None or estimate.status != EstimateStatus.completed:
        raise AppError(
            409, "estimate_not_ready", "Run the estimate to completion first"
        )
    gaps = _estimate_gaps(estimate)
    if not gaps:
        raise AppError(
            400, "no_missing_info", "The latest estimate did not identify missing information"
        )
    injury_type = await _injury_type_or_404(db, session.injury_type_id)
    return await generate_advice(db, injury_type, focus_gaps=gaps)


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
