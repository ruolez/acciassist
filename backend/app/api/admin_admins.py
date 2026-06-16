from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentAdmin, DbSession
from app.errors import AppError
from app.models import AdminUser
from app.schemas import AdminCreateIn, AdminOut
from app.security import hash_password

router = APIRouter()


@router.get("", response_model=list[AdminOut])
async def list_admins(db: DbSession) -> list[AdminUser]:
    result = await db.scalars(select(AdminUser).order_by(AdminUser.created_at))
    return list(result)


@router.post("", response_model=AdminOut, status_code=201)
async def create_admin(data: AdminCreateIn, db: DbSession) -> AdminUser:
    existing = await db.scalar(select(AdminUser).where(AdminUser.email == data.email))
    if existing is not None:
        raise AppError(409, "email_taken", "An admin with that email already exists")
    admin = AdminUser(email=data.email, password_hash=hash_password(data.password))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.delete("/{admin_id}", status_code=204)
async def delete_admin(admin_id: int, current: CurrentAdmin, db: DbSession) -> None:
    if admin_id == current.id:
        raise AppError(400, "cannot_delete_self", "You cannot delete your own account")
    admin = await db.get(AdminUser, admin_id)
    if admin is None:
        raise AppError(404, "not_found", "Admin not found")
    await db.delete(admin)
    await db.commit()
