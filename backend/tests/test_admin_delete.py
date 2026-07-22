from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import (
    Case,
    CaseDocument,
    CaseEstimate,
    CaseUpdate,
    IntakeAnswer,
    IntakeSession,
    Lead,
    User,
)
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


class TestDeleteCase:
    async def test_delete_case_removes_everything(
        self, admin_client, user_client, session_factory
    ):
        cid = await _full_intake_lead(admin_client, user_client, "pat@example.com")
        upload = await user_client.post(
            f"/api/me/cases/{cid}/documents",
            files={"file": ("bill.pdf", PDF_BYTES, "application/pdf")},
        )
        assert upload.status_code == 201
        assert len(_stored_files()) == 1
        posted = await admin_client.post(
            f"/api/admin/cases/{cid}/updates", json={"body": "Reviewing your file."}
        )
        assert posted.status_code == 201

        resp = await admin_client.delete(f"/api/admin/cases/{cid}")
        assert resp.status_code == 204

        assert _stored_files() == []
        async with session_factory() as s:
            assert await s.get(Case, cid) is None
        assert await _count(session_factory, CaseDocument) == 0
        assert await _count(session_factory, CaseUpdate) == 0
        assert await _count(session_factory, IntakeSession) == 0
        assert await _count(session_factory, IntakeAnswer) == 0
        assert await _count(session_factory, CaseEstimate) == 0
        # The intake lead is gone; the user_client fixture's bare lead remains.
        assert await _count(session_factory, Lead) == 1
        async with session_factory() as s:
            user = await s.scalar(select(User).where(User.email == "pat@example.com"))
            assert user is not None

    async def test_delete_case_without_intake(
        self, admin_client, user_client, session_factory
    ):
        cases = (await admin_client.get("/api/admin/cases")).json()
        assert len(cases) == 1
        resp = await admin_client.delete(f"/api/admin/cases/{cases[0]['id']}")
        assert resp.status_code == 204
        assert await _count(session_factory, Case) == 0
        assert await _count(session_factory, Lead) == 0

    async def test_delete_case_404(self, admin_client):
        resp = await admin_client.delete("/api/admin/cases/99999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


class TestDeleteSubmission:
    async def test_delete_submission(self, admin_client, session_factory):
        # Intake without a lead: publish a type, answer, complete.
        itid = (
            await admin_client.post(
                "/api/admin/injury-types", json={"name": "Slip and Fall", "is_published": True}
            )
        ).json()["id"]
        q = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "short_text", "prompt": "What happened?"},
        )
        sid = (
            await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
        ).json()["session_id"]
        await admin_client.post(
            f"/api/intake/{sid}/answers",
            json={"answers": [{"question_id": q.json()["id"], "value": "Wet floor."}]},
        )
        await admin_client.post(f"/api/intake/{sid}/complete")

        resp = await admin_client.delete(f"/api/admin/intake-sessions/{sid}")
        assert resp.status_code == 204
        assert (await admin_client.get("/api/admin/intake-sessions")).json() == []
        assert await _count(session_factory, IntakeAnswer) == 0
        assert await _count(session_factory, CaseEstimate) == 0

    async def test_delete_submission_keeps_linked_case(
        self, admin_client, user_client, session_factory
    ):
        cid = await _full_intake_lead(admin_client, user_client, "pat@example.com")
        detail = (await admin_client.get(f"/api/admin/cases/{cid}")).json()
        sid = detail["intake_session_id"]
        assert sid is not None

        resp = await admin_client.delete(f"/api/admin/intake-sessions/{sid}")
        assert resp.status_code == 204

        detail = await admin_client.get(f"/api/admin/cases/{cid}")
        assert detail.status_code == 200
        assert detail.json()["intake_session_id"] is None
        assert detail.json()["estimate"] is None
        async with session_factory() as s:
            leads = (
                await s.scalars(select(Lead).where(Lead.email == "pat@example.com"))
            ).all()
            assert all(lead.intake_session_id is None for lead in leads)

    async def test_delete_submission_404(self, admin_client):
        resp = await admin_client.delete(
            "/api/admin/intake-sessions/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


class TestDeleteAuth:
    async def test_delete_requires_admin(self, admin_client, make_client):
        anon = await make_client()
        assert (await anon.delete("/api/admin/cases/1")).status_code == 401
        assert (
            await anon.delete(
                "/api/admin/intake-sessions/00000000-0000-0000-0000-000000000000"
            )
        ).status_code == 401
