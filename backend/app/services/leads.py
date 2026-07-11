from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthToken, Case, Lead, TokenPurpose, User
from app.schemas import LeadIn
from app.security import generate_token

CLAIM_TOKEN_TTL = timedelta(days=7)
RESET_TOKEN_TTL = timedelta(hours=1)


async def issue_token(db: AsyncSession, user_id: int, purpose: TokenPurpose) -> str:
    """Invalidate outstanding tokens of the same purpose and mint a fresh one.
    Returns the raw token; only its hash is persisted. Does not commit."""
    now = datetime.now(UTC)
    await db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw, token_hash = generate_token()
    ttl = CLAIM_TOKEN_TTL if purpose == TokenPurpose.account_claim else RESET_TOKEN_TTL
    db.add(
        AuthToken(
            user_id=user_id, token_hash=token_hash, purpose=purpose, expires_at=now + ttl
        )
    )
    return raw


async def process_lead(db: AsyncSession, data: LeadIn) -> tuple[Lead, Case, str | None]:
    """Create the lead, its case, and (for unclaimed users) a fresh account-claim
    token. Returns (lead, case, raw_claim_token_or_None) after one commit."""
    email = data.email.lower()
    lead = Lead(
        intake_session_id=data.intake_session_id,
        name=data.name,
        email=email,
        phone=data.phone,
    )
    db.add(lead)

    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, name=data.name, phone=data.phone)
        db.add(user)
    await db.flush()

    case = Case(user_id=user.id, lead_id=lead.id)
    db.add(case)

    raw_token = None
    if user.password_hash is None:
        raw_token = await issue_token(db, user.id, TokenPurpose.account_claim)

    await db.commit()
    await db.refresh(lead)
    return lead, case, raw_token
