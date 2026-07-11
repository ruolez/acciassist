import re

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  (register tables)
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import AdminUser
from app.security import hash_password


@pytest.fixture(autouse=True)
def _disable_rate_limits(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)


@pytest.fixture
def sent_emails(monkeypatch):
    """Capture outgoing SMTP messages instead of hitting the network."""
    sent: list[tuple[dict, object]] = []

    def _capture(snapshot: dict, msg: object) -> None:
        sent.append((snapshot, msg))

    monkeypatch.setattr("app.services.email._send_via_smtp", _capture)
    return sent


@pytest.fixture(autouse=True)
def _email_uses_test_db(session_factory, monkeypatch):
    """Background notification tasks open their own session — point it at the
    test database instead of the dev one."""
    monkeypatch.setattr("app.services.email.get_session_factory", lambda: session_factory)

_base_url, _ = settings.database_url.rsplit("/", 1)
TEST_DB = "acciassist_test"
TEST_URL = f"{_base_url}/{TEST_DB}"

ADMIN_EMAIL = "tester@example.com"
ADMIN_PASSWORD = "password123"


async def _ensure_test_database() -> None:
    admin_engine = create_async_engine(
        settings.database_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    await admin_engine.dispose()


@pytest_asyncio.fixture
async def engine():
    # Function-scoped + NullPool: every test owns its connections on its own loop.
    await _ensure_test_database()
    eng = create_async_engine(TEST_URL, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def make_client(session_factory):
    """Factory for API clients that share the app/test DB but have their own
    cookie jars (so admin and user sessions can coexist in one test)."""

    async def _override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    clients: list[AsyncClient] = []

    async def _make() -> AsyncClient:
        c = AsyncClient(transport=transport, base_url="http://test")
        clients.append(c)
        return c

    yield _make
    for c in clients:
        await c.aclose()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(make_client):
    return await make_client()


@pytest_asyncio.fixture
async def admin_client(client, session_factory):
    async with session_factory() as s:
        s.add(AdminUser(email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD)))
        await s.commit()
    resp = await client.post(
        "/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 200
    return client


USER_EMAIL = "pat@example.com"
USER_PASSWORD = "userpass123"


async def seed_smtp_settings(session_factory) -> None:
    from app.services.email import get_app_settings

    async with session_factory() as s:
        row = await get_app_settings(s)
        row.smtp_host = "mail.example.com"
        row.from_email = "noreply@example.com"
        row.app_base_url = "https://acciassist.example"
        await s.commit()


def claim_token_from(sent_emails) -> str:
    body = sent_emails[-1][1].get_body(preferencelist=("plain",)).get_content()
    match = re.search(r"claim\?token=([A-Za-z0-9_-]+)", body)
    assert match, f"no claim link in email:\n{body}"
    return match.group(1)


@pytest_asyncio.fixture
async def user_client(make_client, session_factory, sent_emails):
    """A client logged in as a user who came through the lead → claim flow."""
    await seed_smtp_settings(session_factory)
    c = await make_client()
    resp = await c.post(
        "/api/leads", json={"name": "Pat Smith", "email": USER_EMAIL, "phone": "555-1234"}
    )
    assert resp.status_code == 201
    resp = await c.post(
        "/api/auth/claim",
        json={"token": claim_token_from(sent_emails), "password": USER_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return c
