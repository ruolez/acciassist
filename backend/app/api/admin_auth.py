from fastapi import APIRouter, Response
from sqlalchemy import select

from app.config import settings
from app.deps import ADMIN_COOKIE, CurrentAdmin, DbSession
from app.errors import AppError
from app.models import AdminUser
from app.schemas import AdminOut, LoginIn
from app.security import create_access_token, verify_password

router = APIRouter()


def _set_auth_cookie(response: Response, admin_id: int) -> None:
    response.set_cookie(
        ADMIN_COOKIE,
        create_access_token(str(admin_id)),
        httponly=True,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )


@router.post("/login", response_model=AdminOut)
async def login(data: LoginIn, response: Response, db: DbSession) -> AdminUser:
    admin = await db.scalar(select(AdminUser).where(AdminUser.email == data.email))
    valid = (
        admin is not None
        and admin.is_active
        and verify_password(data.password, admin.password_hash)
    )
    if not valid:
        raise AppError(401, "invalid_credentials", "Invalid email or password")
    _set_auth_cookie(response, admin.id)
    return admin


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=AdminOut)
async def me(admin: CurrentAdmin) -> AdminUser:
    return admin
