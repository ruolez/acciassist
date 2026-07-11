from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import CurrentUser, DbSession
from app.errors import AppError
from app.models import Case, InjuryType, IntakeSession, Lead, SummaryTemplate, User
from app.schemas import CaseDetailOut, CaseListOut, CaseUpdateOut, ProfileIn, UserOut
from app.services.summary import render_session_summary

router = APIRouter()


async def _case_context(db: DbSession, case: Case) -> dict:
    """Injury type name + estimate range for a case, via its lead's intake session."""
    row = None
    if case.lead.intake_session_id is not None:
        row = (
            await db.execute(
                select(InjuryType.name, SummaryTemplate.estimate_min, SummaryTemplate.estimate_max)
                .select_from(IntakeSession)
                .join(InjuryType, InjuryType.id == IntakeSession.injury_type_id)
                .outerjoin(
                    SummaryTemplate, SummaryTemplate.injury_type_id == InjuryType.id
                )
                .where(IntakeSession.id == case.lead.intake_session_id)
            )
        ).first()
    return {
        "injury_type_name": row[0] if row else None,
        "estimate_min": row[1] if row else None,
        "estimate_max": row[2] if row else None,
    }


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
            CaseListOut(id=case.id, stage=case.stage, created_at=case.created_at, **context)
        )
    return out


@router.get("/cases/{case_id}", response_model=CaseDetailOut)
async def my_case_detail(case_id: int, user: CurrentUser, db: DbSession) -> CaseDetailOut:
    case = await db.scalar(
        select(Case)
        .where(Case.id == case_id, Case.user_id == user.id)
        .options(selectinload(Case.lead), selectinload(Case.updates))
    )
    if case is None:
        raise AppError(404, "not_found", "Case not found")

    lead: Lead = case.lead
    summary = None
    if lead.intake_session_id is not None:
        session = await db.get(IntakeSession, lead.intake_session_id)
        if session is not None:
            summary = await render_session_summary(db, session)

    context = await _case_context(db, case)
    return CaseDetailOut(
        id=case.id,
        stage=case.stage,
        created_at=case.created_at,
        updates=[CaseUpdateOut.model_validate(u) for u in case.updates],
        summary=summary,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        **context,
    )


@router.patch("/profile", response_model=UserOut)
async def update_profile(data: ProfileIn, user: CurrentUser, db: DbSession) -> User:
    user.name = data.name
    user.phone = data.phone
    await db.commit()
    await db.refresh(user)
    return user
