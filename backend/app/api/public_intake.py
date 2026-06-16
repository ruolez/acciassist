import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DbSession
from app.errors import AppError
from app.models import (
    InjuryType,
    IntakeAnswer,
    IntakeSession,
    IntakeStatus,
    Lead,
    Question,
    SummaryTemplate,
)
from app.schemas import (
    AnswersIn,
    InjuryTypeOut,
    IntakePage,
    IntakeStartIn,
    IntakeStartOut,
    LeadIn,
    LeadOut,
    QuestionOut,
    SummaryOut,
)
from app.services.pagination import build_pages
from app.services.summary import answer_display_value, render_template

router = APIRouter()


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


@router.post("/intake/start", response_model=IntakeStartOut)
async def start_intake(data: IntakeStartIn, db: DbSession) -> IntakeStartOut:
    injury_type = await _published_injury_type(db, data.injury_type_id)
    session = IntakeSession(injury_type_id=injury_type.id)
    db.add(session)
    await db.commit()
    await db.refresh(session)

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


@router.post("/intake/{session_id}/answers", status_code=204)
async def save_answers(
    session_id: uuid.UUID, data: AnswersIn, db: DbSession
) -> None:
    session = await _active_session(db, session_id)
    if session.status == IntakeStatus.completed:
        raise AppError(409, "already_completed", "This intake has already been submitted")
    existing = {
        a.question_id: a
        for a in await db.scalars(
            select(IntakeAnswer).where(IntakeAnswer.session_id == session_id)
        )
    }
    for answer in data.answers:
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


async def _render_summary(db: DbSession, session: IntakeSession) -> SummaryOut:
    questions = await _questions_for(db, session.injury_type_id)
    answers = {
        a.question_id: a.value
        for a in await db.scalars(
            select(IntakeAnswer).where(IntakeAnswer.session_id == session.id)
        )
    }
    values: dict[str, str] = {}
    for q in questions:
        labels = {o.value: o.label for o in q.options}
        values[q.slug] = answer_display_value(q.type, answers.get(q.id), labels)

    tmpl = await db.scalar(
        select(SummaryTemplate).where(
            SummaryTemplate.injury_type_id == session.injury_type_id
        )
    )
    if tmpl is None:
        return SummaryOut(
            body="",
            estimate_min=None,
            estimate_max=None,
            estimate_note="Upon closer inspection our experts will provide a better estimate.",
        )
    return SummaryOut(
        body=render_template(tmpl.body, values),
        estimate_min=tmpl.estimate_min,
        estimate_max=tmpl.estimate_max,
        estimate_note=tmpl.estimate_note,
    )


@router.post("/intake/{session_id}/complete", response_model=SummaryOut)
async def complete_intake(session_id: uuid.UUID, db: DbSession) -> SummaryOut:
    session = await _active_session(db, session_id)
    if session.status != IntakeStatus.completed:
        session.status = IntakeStatus.completed
        session.completed_at = datetime.now(UTC)
        await db.commit()
    return await _render_summary(db, session)


@router.get("/intake/{session_id}/summary", response_model=SummaryOut)
async def get_summary(session_id: uuid.UUID, db: DbSession) -> SummaryOut:
    session = await _active_session(db, session_id)
    return await _render_summary(db, session)


@router.post("/leads", response_model=LeadOut, status_code=201)
async def create_lead(data: LeadIn, db: DbSession) -> Lead:
    lead = Lead(
        intake_session_id=data.intake_session_id,
        name=data.name,
        email=data.email,
        phone=data.phone,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead
