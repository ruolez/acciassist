from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

# Reused intake helpers: same validation and upsert path as the public wizard.
from app.api.public_intake import _questions_for, upsert_answers
from app.deps import CurrentUser, DbSession
from app.errors import AppError
from app.models import (
    Case,
    CaseEstimate,
    EstimateStatus,
    InjuryType,
    IntakeAnswer,
    IntakeSession,
    Lead,
    Question,
    SummaryTemplate,
    User,
)
from app.schemas import (
    AnswersIn,
    CaseDetailOut,
    CaseListOut,
    CaseUpdateOut,
    FollowupOut,
    IntakePage,
    ProfileIn,
    QuestionOut,
    UserOut,
)
from app.services.estimates import schedule_estimate
from app.services.pagination import build_pages
from app.services.summary import render_session_summary

router = APIRouter()


async def _case_context(db: DbSession, case: Case) -> dict:
    """Injury type name, estimate range, and follow-up state for a case.

    The range prefers the live pipeline estimate (it narrows after follow-up
    answers); the static template range is the fallback."""
    context: dict = {
        "injury_type_name": None,
        "estimate_min": None,
        "estimate_max": None,
        "followup_pending": False,
    }
    session_id = case.lead.intake_session_id
    if session_id is None:
        return context
    row = (
        await db.execute(
            select(InjuryType.name, SummaryTemplate.estimate_min, SummaryTemplate.estimate_max)
            .select_from(IntakeSession)
            .join(InjuryType, InjuryType.id == IntakeSession.injury_type_id)
            .outerjoin(SummaryTemplate, SummaryTemplate.injury_type_id == InjuryType.id)
            .where(IntakeSession.id == session_id)
        )
    ).first()
    if row:
        context["injury_type_name"] = row[0]
        context["estimate_min"] = row[1]
        context["estimate_max"] = row[2]

    estimate = await db.scalar(
        select(CaseEstimate).where(CaseEstimate.intake_session_id == session_id)
    )
    if (
        estimate is not None
        and estimate.status == EstimateStatus.completed
        and estimate.payout_min is not None
    ):
        context["estimate_min"] = estimate.payout_min
        context["estimate_max"] = estimate.payout_max

    session = await db.get(IntakeSession, session_id)
    followup_total = await db.scalar(
        select(func.count())
        .select_from(Question)
        .where(
            Question.injury_type_id == session.injury_type_id,
            Question.phase == "follow_up",
        )
    )
    context["followup_pending"] = bool(
        followup_total and session.followup_completed_at is None
    )
    context["_followup_total"] = int(followup_total or 0)
    context["_session"] = session
    context["_estimate"] = estimate
    return context


async def _my_case(db: DbSession, case_id: int, user_id: int) -> Case:
    case = await db.scalar(
        select(Case)
        .where(Case.id == case_id, Case.user_id == user_id)
        .options(selectinload(Case.lead), selectinload(Case.updates))
    )
    if case is None:
        raise AppError(404, "not_found", "Case not found")
    return case


@router.get("/cases", response_model=list[CaseListOut])
async def my_cases(user: CurrentUser, db: DbSession) -> list[CaseListOut]:
    cases = await db.scalars(
        select(Case)
        .where(Case.user_id == user.id)
        .order_by(Case.created_at.desc())
        .options(selectinload(Case.lead))
    )
    out = []
    for case in cases:
        context = await _case_context(db, case)
        out.append(
            CaseListOut(
                id=case.id,
                stage=case.stage,
                created_at=case.created_at,
                **{k: v for k, v in context.items() if not k.startswith("_")},
            )
        )
    return out


async def _case_detail_payload(db: DbSession, case: Case) -> CaseDetailOut:
    lead: Lead = case.lead
    context = await _case_context(db, case)
    session: IntakeSession | None = context.pop("_session", None)
    estimate: CaseEstimate | None = context.pop("_estimate", None)
    followup_total: int = context.pop("_followup_total", 0)

    summary = await render_session_summary(db, session) if session is not None else None
    refined = bool(
        session is not None
        and session.followup_completed_at is not None
        and estimate is not None
        and estimate.status == EstimateStatus.completed
    )
    return CaseDetailOut(
        id=case.id,
        stage=case.stage,
        created_at=case.created_at,
        updates=[CaseUpdateOut.model_validate(u) for u in case.updates],
        summary=summary,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        followup_total=followup_total,
        estimate_status=estimate.status.value if estimate else None,
        estimate_refined=refined,
        **context,
    )


@router.get("/cases/{case_id}", response_model=CaseDetailOut)
async def my_case_detail(case_id: int, user: CurrentUser, db: DbSession) -> CaseDetailOut:
    case = await _my_case(db, case_id, user.id)
    return await _case_detail_payload(db, case)


async def _followup_session(db: DbSession, case: Case) -> IntakeSession:
    if case.lead.intake_session_id is None:
        raise AppError(404, "no_intake", "This case has no questionnaire")
    session = await db.get(IntakeSession, case.lead.intake_session_id)
    if session is None:
        raise AppError(404, "no_intake", "This case has no questionnaire")
    return session


@router.get("/cases/{case_id}/follow-up", response_model=FollowupOut)
async def my_followup(case_id: int, user: CurrentUser, db: DbSession) -> FollowupOut:
    case = await _my_case(db, case_id, user.id)
    session = await _followup_session(db, case)
    questions = await _questions_for(db, session.injury_type_id, phase="follow_up")
    pages = [
        IntakePage(page_index=i, questions=[QuestionOut.model_validate(q) for q in group])
        for i, group in enumerate(build_pages(questions))
    ]
    question_ids = {q.id for q in questions}
    answers = {
        a.question_id: a.value
        for a in await db.scalars(
            select(IntakeAnswer).where(IntakeAnswer.session_id == session.id)
        )
        if a.question_id in question_ids
    }
    return FollowupOut(
        pages=pages,
        total_pages=len(pages),
        completed=session.followup_completed_at is not None,
        answers=answers,
    )


@router.post("/cases/{case_id}/follow-up/answers", status_code=204)
async def save_followup_answers(
    case_id: int, data: AnswersIn, user: CurrentUser, db: DbSession
) -> None:
    case = await _my_case(db, case_id, user.id)
    session = await _followup_session(db, case)
    if session.followup_completed_at is not None:
        raise AppError(
            409, "followup_completed", "The follow-up questionnaire is already submitted"
        )
    questions = {
        q.id: q for q in await _questions_for(db, session.injury_type_id, phase="follow_up")
    }
    await upsert_answers(db, session.id, questions, data)
    await db.commit()


@router.post("/cases/{case_id}/follow-up/complete", response_model=CaseDetailOut)
async def complete_followup(
    case_id: int, user: CurrentUser, db: DbSession, background_tasks: BackgroundTasks
) -> CaseDetailOut:
    case = await _my_case(db, case_id, user.id)
    session = await _followup_session(db, case)
    if session.followup_completed_at is None:
        session.followup_completed_at = datetime.now(UTC)
        await db.commit()
        # Re-run the pipeline with the richer answers — the refined estimate.
        await schedule_estimate(db, session, background_tasks)
    return await _case_detail_payload(db, case)


@router.patch("/profile", response_model=UserOut)
async def update_profile(data: ProfileIn, user: CurrentUser, db: DbSession) -> User:
    user.name = data.name
    user.phone = data.phone
    await db.commit()
    await db.refresh(user)
    return user
