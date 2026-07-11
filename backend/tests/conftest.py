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
async def client(session_factory):
    async def _override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


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
