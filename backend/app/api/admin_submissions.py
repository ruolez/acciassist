import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DbSession
from app.errors import AppError
from app.models import IntakeSession, Lead
from app.schemas import IntakeSessionDetailOut, IntakeSessionOut, LeadOut

router = APIRouter()


@router.get("/intake-sessions", response_model=list[IntakeSessionOut])
async def list_sessions(db: DbSession) -> list[IntakeSession]:
    rows = await db.scalars(
        select(IntakeSession).order_by(IntakeSession.started_at.desc())
    )
    return list(rows)


@router.get("/intake-sessions/{session_id}", response_model=IntakeSessionDetailOut)
async def get_session(session_id: uuid.UUID, db: DbSession) -> IntakeSession:
    session = await db.scalar(
        select(IntakeSession)
        .where(IntakeSession.id == session_id)
        .options(selectinload(IntakeSession.answers))
    )
    if session is None:
        raise AppError(404, "not_found", "Intake session not found")
    return session


@router.get("/leads", response_model=list[LeadOut])
async def list_leads(db: DbSession) -> list[Lead]:
    rows = await db.scalars(select(Lead).order_by(Lead.created_at.desc()))
    return list(rows)
