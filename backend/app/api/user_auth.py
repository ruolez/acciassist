from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy import select

from app.config import settings
from app.deps import USER_COOKIE, CurrentUser, DbSession
from app.errors import AppError
from app.models import AuthToken, Case, TokenPurpose, User
from app.schemas import (
    ClaimIn,
    ClaimVerifyIn,
    ClaimVerifyOut,
    ForgotPasswordIn,
    LoginIn,
    ResendClaimIn,
    ResetPasswordIn,
    UserOut,
)
from app.security import create_access_token, hash_password, hash_token, verify_password
from app.services.leads import issue_token
from app.services.notifications import notify_lead_received, send_password_reset
from app.services.ratelimit import rate_limit

router = APIRouter()

_login_limit = rate_limit("user_login", limit=5, window_seconds=60)
_token_request_limit = rate_limit("user_token_request", limit=5, window_seconds=3600)


def _set_auth_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        USER_COOKIE,
        create_access_token(str(user_id), scope="user"),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )


async def _valid_token(db: DbSession, raw: str, purpose: TokenPurpose) -> AuthToken:
    token = await db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(raw), AuthToken.purpose == purpose
        )
    )
    if token is None:
        raise AppError(400, "invalid_token", "This link is not valid")
    if token.used_at is not None:
        raise AppError(400, "token_used", "This link has already been used")
    if token.expires_at < datetime.now(UTC):
        raise AppError(400, "token_expired", "This link has expired")
    return token


@router.post("/claim/verify", response_model=ClaimVerifyOut)
async def verify_claim(data: ClaimVerifyIn, db: DbSession) -> ClaimVerifyOut:
    token = await _valid_token(db, data.token, TokenPurpose.account_claim)
    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise AppError(400, "invalid_token", "This link is not valid")
    return ClaimVerifyOut(email=user.email, name=user.name)


@router.post("/claim", response_model=UserOut)
async def claim_account(data: ClaimIn, response: Response, db: DbSession) -> User:
    token = await _valid_token(db, data.token, TokenPurpose.account_claim)
    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise AppError(400, "invalid_token", "This link is not valid")
    now = datetime.now(UTC)
    user.password_hash = hash_password(data.password)
    user.claimed_at = now
    token.used_at = now
    await db.commit()
    _set_auth_cookie(response, user.id)
    return user


@router.post("/claim/resend", dependencies=[Depends(_token_request_limit)])
async def resend_claim(
    data: ResendClaimIn, db: DbSession, background_tasks: BackgroundTasks
) -> dict[str, bool]:
    # Always {ok: true} so the endpoint can't be used to enumerate accounts.
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if user is not None and user.is_active and user.password_hash is None:
        lead_id = await db.scalar(
            select(Case.lead_id)
            .where(Case.user_id == user.id)
            .order_by(Case.id.desc())
            .limit(1)
        )
        if lead_id is not None:
            raw = await issue_token(db, user.id, TokenPurpose.account_claim)
            await db.commit()
            background_tasks.add_task(notify_lead_received, lead_id, raw)
    return {"ok": True}


@router.post("/login", response_model=UserOut, dependencies=[Depends(_login_limit)])
async def login(data: LoginIn, response: Response, db: DbSession) -> User:
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    valid = (
        user is not None
        and user.is_active
        and user.password_hash is not None
        and verify_password(data.password, user.password_hash)
    )
    if not valid:
        raise AppError(401, "invalid_credentials", "Invalid email or password")
    _set_auth_cookie(response, user.id)
    return user


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(
        USER_COOKIE, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure
    )
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/forgot-password", dependencies=[Depends(_token_request_limit)])
async def forgot_password(
    data: ForgotPasswordIn, db: DbSession, background_tasks: BackgroundTasks
) -> dict[str, bool]:
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if user is not None and user.is_active and user.password_hash is not None:
        raw = await issue_token(db, user.id, TokenPurpose.password_reset)
        await db.commit()
        background_tasks.add_task(send_password_reset, user.id, raw)
    return {"ok": True}


@router.post("/reset-password")
async def reset_password(data: ResetPasswordIn, db: DbSession) -> dict[str, bool]:
    token = await _valid_token(db, data.token, TokenPurpose.password_reset)
    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise AppError(400, "invalid_token", "This link is not valid")
    user.password_hash = hash_password(data.password)
    token.used_at = datetime.now(UTC)
    await db.commit()
    return {"ok": True}
