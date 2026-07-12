import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DbSession
from app.errors import AppError
from app.models import (
    CaseEstimate,
    EstimateStatus,
    InjuryType,
    IntakeAnswer,
    IntakeSession,
    IntakeStatus,
    Lead,
    Question,
    QuestionType,
)
from app.schemas import (
    AnswersIn,
    InjuryTypeOut,
    IntakePage,
    IntakeStartIn,
    IntakeStartOut,
    LeadIn,
    LeadOut,
    PublicEstimateOut,
    QuestionOut,
    SummaryOut,
)
from app.services.estimates import schedule_estimate
from app.services.leads import process_lead
from app.services.notifications import notify_lead_received
from app.services.pagination import build_pages
from app.services.ratelimit import rate_limit
from app.services.summary import render_session_summary

router = APIRouter()

_intake_start_limit = rate_limit("intake_start", limit=20, window_seconds=3600)
_leads_limit = rate_limit("leads", limit=10, window_seconds=3600)


def _config_number(config: dict, key: str) -> float | None:
    """Read a numeric bound from config, ignoring legacy junk values."""
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _text_cap(config: dict, type_cap: int) -> int:
    max_length = config.get("max_length")
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length < 1:
        return type_cap
    return min(type_cap, max_length)


def _validate_answer(question: Question, value: object) -> None:
    """Enforce the JSON shape each question type expects; None means cleared.
    Admin-configured bounds (config JSONB) are read defensively — rows saved
    before config was typed may hold arbitrary values."""
    if value is None:
        return
    error = AppError(
        422, "invalid_answer", f"Invalid answer for question '{question.slug}'"
    )
    config = question.config or {}
    match question.type:
        case QuestionType.yes_no:
            if not isinstance(value, bool):
                raise error
        case QuestionType.number:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise error
            minimum = _config_number(config, "min")
            maximum = _config_number(config, "max")
            if minimum is not None and value < minimum:
                raise error
            if maximum is not None and value > maximum:
                raise error
        case QuestionType.single_choice:
            allowed = {o.value for o in question.options}
            if not isinstance(value, str) or value not in allowed:
                raise error
        case QuestionType.multi_choice:
            allowed = {o.value for o in question.options}
            if not isinstance(value, list) or not all(
                isinstance(v, str) and v in allowed for v in value
            ):
                raise error
        case QuestionType.date:
            if not isinstance(value, str):
                raise error
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                raise error from None
            # +1 day of grace: the patient's local "today" may be ahead of UTC.
            if config.get("disallow_future") is True and parsed > date.today() + timedelta(
                days=1
            ):
                raise error
        case QuestionType.short_text:
            if not isinstance(value, str) or len(value) > _text_cap(config, 500):
                raise error
        case QuestionType.long_text:
            if not isinstance(value, str) or len(value) > _text_cap(config, 10_000):
                raise error


async def _published_injury_type(db: DbSession, injury_type_id: int) -> InjuryType:
    obj = await db.scalar(
        select(InjuryType).where(
            InjuryType.id == injury_type_id, InjuryType.is_published.is_(True)
        )
    )
    if obj is None:
        raise AppError(404, "not_found", "Injury type not available")
    return obj


async def _active_session(db: DbSession, session_id: uuid.UUID) -> IntakeSession:
    session = await db.get(IntakeSession, session_id)
    if session is None:
        raise AppError(404, "not_found", "Intake session not found")
    return session


async def _questions_for(db: DbSession, injury_type_id: int) -> list[Question]:
    rows = await db.scalars(
        select(Question)
        .where(Question.injury_type_id == injury_type_id)
        .order_by(Question.display_order)
        .options(selectinload(Question.options))
    )
    return list(rows)


@router.get("/injury-types", response_model=list[InjuryTypeOut])
async def public_injury_types(db: DbSession) -> list[InjuryType]:
    rows = await db.scalars(
        select(InjuryType)
        .where(InjuryType.is_published.is_(True))
        .order_by(InjuryType.display_order)
    )
    return list(rows)


async def _start_payload(
    db: DbSession, injury_type: InjuryType, session: IntakeSession
) -> IntakeStartOut:
    questions = await _questions_for(db, injury_type.id)
    pages = [
        IntakePage(
            page_index=i,
            questions=[QuestionOut.model_validate(q) for q in group],
        )
        for i, group in enumerate(build_pages(questions))
    ]
    return IntakeStartOut(
        session_id=session.id,
        injury_type=InjuryTypeOut.model_validate(injury_type),
        pages=pages,
        total_pages=len(pages),
    )


@router.post(
    "/intake/start", response_model=IntakeStartOut, dependencies=[Depends(_intake_start_limit)]
)
async def start_intake(data: IntakeStartIn, db: DbSession) -> IntakeStartOut:
    injury_type = await _published_injury_type(db, data.injury_type_id)
    session = IntakeSession(injury_type_id=injury_type.id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return await _start_payload(db, injury_type, session)


@router.get("/intake/{session_id}/pages", response_model=IntakeStartOut)
async def get_session_pages(session_id: uuid.UUID, db: DbSession) -> IntakeStartOut:
    """Current questionnaire for an existing session, so a resumed wizard can
    refresh a cached snapshot after the admin edits questions."""
    session = await _active_session(db, session_id)
    injury_type = await db.get(InjuryType, session.injury_type_id)
    if injury_type is None or not injury_type.is_published:
        raise AppError(404, "not_found", "Injury type not available")
    return await _start_payload(db, injury_type, session)


@router.post("/intake/{session_id}/answers", status_code=204)
async def save_answers(
    session_id: uuid.UUID, data: AnswersIn, db: DbSession
) -> None:
    session = await _active_session(db, session_id)
    if session.status == IntakeStatus.completed:
        raise AppError(409, "already_completed", "This intake has already been submitted")
    questions = {q.id: q for q in await _questions_for(db, session.injury_type_id)}
    existing = {
        a.question_id: a
        for a in await db.scalars(
            select(IntakeAnswer).where(IntakeAnswer.session_id == session_id)
        )
    }
    for answer in data.answers:
        question = questions.get(answer.question_id)
        if question is None:
            raise AppError(
                422, "invalid_answer", "Answer references a question outside this intake"
            )
        _validate_answer(question, answer.value)
        if answer.question_id in existing:
            existing[answer.question_id].value = answer.value
        else:
            db.add(
                IntakeAnswer(
                    session_id=session_id,
                    question_id=answer.question_id,
                    value=answer.value,
                )
            )
    await db.commit()


@router.post("/intake/{session_id}/complete", response_model=SummaryOut)
async def complete_intake(
    session_id: uuid.UUID, db: DbSession, background_tasks: BackgroundTasks
) -> SummaryOut:
    session = await _active_session(db, session_id)
    if session.status != IntakeStatus.completed:
        session.status = IntakeStatus.completed
        session.completed_at = datetime.now(UTC)
        await db.commit()
        await schedule_estimate(db, session, background_tasks)
    return await render_session_summary(db, session)


def _public_estimate(estimate: CaseEstimate) -> PublicEstimateOut:
    """Allowlist projection of the assembled result — pipeline internals are
    never exposed to patients. Pre-pipeline rows (no `result`) still return
    the plain payout range."""
    r = estimate.result or {}
    gated = r.get("gated")
    warnings = [
        {
            "code": w.get("code", ""),
            "severity": w.get("severity", "info"),
            "message": w.get("message", ""),
            "deadline": w.get("deadline"),
        }
        for w in (r.get("warnings") or [])
        if w.get("message")
    ]
    return PublicEstimateOut(
        status="completed",
        payout_min=estimate.payout_min,
        payout_max=estimate.payout_max,
        net_min=estimate.net_min,
        net_max=estimate.net_max,
        fee_pct_assumed=r.get("fee_pct"),
        drivers=r.get("drivers"),
        reducers=r.get("reducers"),
        improvements=r.get("improvements"),
        warnings=warnings or None,
        gated=gated if isinstance(gated, dict) else None,
        disclaimer=r.get("disclaimer"),
    )


@router.get("/intake/{session_id}/estimate", response_model=PublicEstimateOut)
async def get_estimate(session_id: uuid.UUID, db: DbSession) -> PublicEstimateOut:
    await _active_session(db, session_id)
    estimate = await db.scalar(
        select(CaseEstimate).where(CaseEstimate.intake_session_id == session_id)
    )
    if estimate is None:
        return PublicEstimateOut(status="none")
    if estimate.status == EstimateStatus.completed:
        return _public_estimate(estimate)
    return PublicEstimateOut(status=estimate.status.value)


@router.get("/intake/{session_id}/summary", response_model=SummaryOut)
async def get_summary(session_id: uuid.UUID, db: DbSession) -> SummaryOut:
    session = await _active_session(db, session_id)
    return await render_session_summary(db, session)


@router.post(
    "/leads", response_model=LeadOut, status_code=201, dependencies=[Depends(_leads_limit)]
)
async def create_lead(
    data: LeadIn, db: DbSession, background_tasks: BackgroundTasks
) -> Lead:
    lead, _, raw_claim_token = await process_lead(db, data)
    # Email delivery happens after the response; a send failure is recorded in
    # email_log and can never fail the lead capture itself.
    background_tasks.add_task(notify_lead_received, lead.id, raw_claim_token)
    return lead
