import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DbSession
from app.errors import AppError
from app.models import CaseEstimate, InjuryType, IntakeSession, Lead
from app.schemas import (
    AnswerOut,
    CaseEstimateAdminOut,
    IntakeSessionDetailOut,
    IntakeSessionOut,
    LeadOut,
)

router = APIRouter()


@router.get("/intake-sessions", response_model=list[IntakeSessionOut])
async def list_sessions(db: DbSession) -> list[IntakeSessionOut]:
    sessions = list(
        await db.scalars(select(IntakeSession).order_by(IntakeSession.started_at.desc()))
    )
    type_names = dict((await db.execute(select(InjuryType.id, InjuryType.name))).all())
    session_ids = [s.id for s in sessions]
    estimates: dict[uuid.UUID, CaseEstimate] = {}
    leads: dict[uuid.UUID, Lead] = {}
    if session_ids:
        for est in await db.scalars(
            select(CaseEstimate).where(CaseEstimate.intake_session_id.in_(session_ids))
        ):
            estimates[est.intake_session_id] = est
        for lead in await db.scalars(
            select(Lead).where(Lead.intake_session_id.in_(session_ids))
        ):
            if lead.intake_session_id is not None:
                leads[lead.intake_session_id] = lead
    out: list[IntakeSessionOut] = []
    for s in sessions:
        est = estimates.get(s.id)
        lead = leads.get(s.id)
        out.append(
            IntakeSessionOut(
                id=s.id,
                injury_type_id=s.injury_type_id,
                status=s.status,
                started_at=s.started_at,
                completed_at=s.completed_at,
                injury_type_name=type_names.get(s.injury_type_id),
                lead_name=lead.name if lead else None,
                payout_min=est.payout_min if est else None,
                payout_max=est.payout_max if est else None,
                estimate_status=est.status if est else None,
            )
        )
    return out


@router.get("/intake-sessions/{session_id}", response_model=IntakeSessionDetailOut)
async def get_session(session_id: uuid.UUID, db: DbSession) -> IntakeSessionDetailOut:
    session = await db.scalar(
        select(IntakeSession)
        .where(IntakeSession.id == session_id)
        .options(selectinload(IntakeSession.answers))
    )
    if session is None:
        raise AppError(404, "not_found", "Intake session not found")
    estimate = await db.scalar(
        select(CaseEstimate).where(CaseEstimate.intake_session_id == session_id)
    )
    return IntakeSessionDetailOut(
        id=session.id,
        injury_type_id=session.injury_type_id,
        status=session.status,
        started_at=session.started_at,
        completed_at=session.completed_at,
        answers=[AnswerOut.model_validate(a) for a in session.answers],
        estimate=CaseEstimateAdminOut.model_validate(estimate) if estimate else None,
    )


@router.delete("/intake-sessions/{session_id}", status_code=204)
async def delete_session(session_id: uuid.UUID, db: DbSession) -> None:
    """Hard-delete an intake session, its answers (ORM cascade) and estimate
    (DB CASCADE). A referencing lead survives with intake_session_id = NULL."""
    session = await db.scalar(
        select(IntakeSession)
        .where(IntakeSession.id == session_id)
        .options(selectinload(IntakeSession.answers))
    )
    if session is None:
        raise AppError(404, "not_found", "Intake session not found")
    await db.delete(session)
    await db.commit()


@router.get("/leads", response_model=list[LeadOut])
async def list_leads(db: DbSession) -> list[Lead]:
    rows = await db.scalars(select(Lead).order_by(Lead.created_at.desc()))
    return list(rows)
