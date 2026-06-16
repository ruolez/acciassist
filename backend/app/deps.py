from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import AppError
from app.models import AdminUser
from app.security import decode_access_token

ADMIN_COOKIE = "admin_token"

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_admin(
    db: DbSession,
    admin_token: Annotated[str | None, Cookie(alias=ADMIN_COOKIE)] = None,
) -> AdminUser:
    if not admin_token:
        raise AppError(401, "unauthenticated", "Authentication required")
    subject = decode_access_token(admin_token)
    if subject is None:
        raise AppError(401, "invalid_token", "Invalid or expired session")
    admin = await db.scalar(select(AdminUser).where(AdminUser.id == int(subject)))
    if admin is None or not admin.is_active:
        raise AppError(401, "inactive_admin", "Admin account is not active")
    return admin


CurrentAdmin = Annotated[AdminUser, Depends(get_current_admin)]
