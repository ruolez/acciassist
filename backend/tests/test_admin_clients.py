from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Case, CaseDocument, IntakeAnswer, IntakeSession, Lead, User
from tests.conftest import seed_smtp_settings
from tests.test_cases import _full_intake_lead

PDF_BYTES = b"%PDF-1.4 fake-but-plausible-pdf-bytes"


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


def _stored_files() -> list[Path]:
    root = Path(settings.upload_dir)
    return [p for p in root.glob("*") if p.is_file()] if root.exists() else []


async def _count(session_factory, model) -> int:
    async with session_factory() as s:
        return await s.scalar(select(func.count()).select_from(model))


class TestListClients:
    async def test_lists_claimed_and_invited_clients(
        self, admin_client, user_client, session_factory
    ):
        await seed_smtp_settings(session_factory)
        resp = await admin_client.post(
            "/api/leads",
            json={"name": "New Lead", "email": "invited@example.com", "phone": None},
        )
        assert resp.status_code == 201

        clients = (await admin_client.get("/api/admin/clients")).json()
        by_email = {c["email"]: c for c in clients}
        assert set(by_email) == {"pat@example.com", "invited@example.com"}

        pat = by_email["pat@example.com"]
        assert pat["claimed"] is True
        assert pat["last_login_at"] is not None  # claiming counts as a sign-in
        assert pat["case_count"] == 1

        invited = by_email["invited@example.com"]
        assert invited["claimed"] is False
        assert invited["last_login_at"] is None
        assert invited["case_count"] == 1

    async def test_login_updates_last_login(self, admin_client, user_client, make_client):
        fresh = await make_client()
        first = next(
            c
            for c in (await admin_client.get("/api/admin/clients")).json()
            if c["email"] == "pat@example.com"
        )["last_login_at"]
        resp = await fresh.post(
            "/api/auth/login", json={"email": "pat@example.com", "password": "userpass123"}
        )
        assert resp.status_code == 200
        after = next(
            c
            for c in (await admin_client.get("/api/admin/clients")).json()
            if c["email"] == "pat@example.com"
        )["last_login_at"]
        assert after is not None and after >= first


class TestDeleteClient:
    async def test_delete_removes_account_and_all_case_data(
        self, admin_client, user_client, session_factory, sent_emails
    ):
        cid = await _full_intake_lead(admin_client, user_client, "pat@example.com")
        upload = await user_client.post(
            f"/api/me/cases/{cid}/documents",
            files={"file": ("bill.pdf", PDF_BYTES, "application/pdf")},
        )
        assert upload.status_code == 201
        assert len(_stored_files()) == 1

        uid = next(
            c
            for c in (await admin_client.get("/api/admin/clients")).json()
            if c["email"] == "pat@example.com"
        )["id"]
        emails_before = len(sent_emails)

        resp = await admin_client.delete(f"/api/admin/clients/{uid}")
        assert resp.status_code == 204

        assert _stored_files() == []
        assert await _count(session_factory, User) == 0
        assert await _count(session_factory, Case) == 0
        assert await _count(session_factory, Lead) == 0
        assert await _count(session_factory, CaseDocument) == 0
        assert await _count(session_factory, IntakeSession) == 0
        assert await _count(session_factory, IntakeAnswer) == 0
        assert len(sent_emails) == emails_before  # notify defaults to off

    async def test_delete_with_notify_sends_email(
        self, admin_client, user_client, sent_emails
    ):
        uid = next(
            c
            for c in (await admin_client.get("/api/admin/clients")).json()
            if c["email"] == "pat@example.com"
        )["id"]
        resp = await admin_client.delete(f"/api/admin/clients/{uid}?notify=true")
        assert resp.status_code == 204
        msg = sent_emails[-1][1]
        assert msg["To"] == "pat@example.com"
        assert "deleted" in msg["Subject"].lower()

    async def test_delete_client_404(self, admin_client):
        resp = await admin_client.delete("/api/admin/clients/99999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    async def test_requires_admin(self, admin_client, make_client):
        anon = await make_client()
        assert (await anon.get("/api/admin/clients")).status_code == 401
        assert (await anon.delete("/api/admin/clients/1")).status_code == 401
