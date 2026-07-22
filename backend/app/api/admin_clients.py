from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DbSession
from app.errors import AppError
from app.models import Case, User
from app.schemas import AdminClientOut
from app.services.case_purge import purge_case
from app.services.documents import delete_stored_file
from app.services.notifications import notify_account_deleted

router = APIRouter()


@router.get("/clients", response_model=list[AdminClientOut])
async def list_clients(db: DbSession) -> list[AdminClientOut]:
    counts = dict(
        (
            await db.execute(
                select(Case.user_id, func.count()).group_by(Case.user_id)
            )
        ).all()
    )
    users = await db.scalars(select(User).order_by(User.created_at.desc()))
    return [
        AdminClientOut(
            id=u.id,
            email=u.email,
            name=u.name,
            phone=u.phone,
            claimed=u.password_hash is not None,
            created_at=u.created_at,
            claimed_at=u.claimed_at,
            last_login_at=u.last_login_at,
            case_count=counts.get(u.id, 0),
        )
        for u in users
    ]


@router.delete("/clients/{user_id}", status_code=204)
async def delete_client(
    user_id: int,
    db: DbSession,
    background_tasks: BackgroundTasks,
    notify: bool = False,
) -> None:
    """Hard-delete a client account and every case that belongs to it — each
    case's documents (rows + stored files), updates, lead, and intake session.
    Auth tokens go via DB CASCADE. With ``notify=true`` the client is emailed
    about the deletion after it completes."""
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(404, "not_found", "Client not found")
    email, name = user.email, user.name
    cases = await db.scalars(
        select(Case)
        .where(Case.user_id == user_id)
        .options(
            selectinload(Case.lead),
            selectinload(Case.documents),
            selectinload(Case.updates),
        )
    )
    docs = []
    for case in cases:
        docs.extend(await purge_case(db, case))
    await db.delete(user)
    await db.commit()
    # Unlink after commit: a crash here leaves only harmless orphan files,
    # never live rows pointing at deleted files.
    for doc in docs:
        delete_stored_file(doc)
    if notify:
        background_tasks.add_task(notify_account_deleted, email, name)
