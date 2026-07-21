import pytest

from app.config import settings
from tests.conftest import claim_token_from

PDF_BYTES = b"%PDF-1.4 fake-but-plausible-pdf-bytes"


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


async def _case_id(user_client) -> int:
    cases = (await user_client.get("/api/me/cases")).json()
    return cases[0]["id"]


def _pdf(name: str = "hospital-bill.pdf") -> dict:
    return {"file": (name, PDF_BYTES, "application/pdf")}


class TestClientDocuments:
    async def test_upload_list_download_roundtrip(self, user_client):
        cid = await _case_id(user_client)
        resp = await user_client.post(f"/api/me/cases/{cid}/documents", files=_pdf())
        assert resp.status_code == 201, resp.text
        doc = resp.json()
        assert doc["original_name"] == "hospital-bill.pdf"
        assert doc["content_type"] == "application/pdf"
        assert doc["size_bytes"] == len(PDF_BYTES)

        listing = (await user_client.get(f"/api/me/cases/{cid}/documents")).json()
        assert [d["id"] for d in listing] == [doc["id"]]

        dl = await user_client.get(
            f"/api/me/cases/{cid}/documents/{doc['id']}/download"
        )
        assert dl.status_code == 200
        assert dl.content == PDF_BYTES
        assert "hospital-bill.pdf" in dl.headers["content-disposition"]

    async def test_rejects_unsupported_type(self, user_client):
        cid = await _case_id(user_client)
        resp = await user_client.post(
            f"/api/me/cases/{cid}/documents",
            files={"file": ("virus.exe", b"MZ...", "application/octet-stream")},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "unsupported_file_type"

    async def test_rejects_oversized_file(self, user_client, monkeypatch):
        monkeypatch.setattr(settings, "max_upload_mb", 1)
        cid = await _case_id(user_client)
        big = b"x" * (1024 * 1024 + 1)
        resp = await user_client.post(
            f"/api/me/cases/{cid}/documents",
            files={"file": ("scan.pdf", big, "application/pdf")},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "file_too_large"

    async def test_rejects_empty_file(self, user_client):
        cid = await _case_id(user_client)
        resp = await user_client.post(
            f"/api/me/cases/{cid}/documents",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "empty_file"

    async def test_enforces_per_case_limit(self, user_client, monkeypatch):
        monkeypatch.setattr(settings, "max_documents_per_case", 1)
        cid = await _case_id(user_client)
        first = await user_client.post(f"/api/me/cases/{cid}/documents", files=_pdf())
        assert first.status_code == 201
        second = await user_client.post(f"/api/me/cases/{cid}/documents", files=_pdf())
        assert second.status_code == 422
        assert second.json()["error"]["code"] == "too_many_documents"

    async def test_delete_removes_document(self, user_client):
        cid = await _case_id(user_client)
        doc = (
            await user_client.post(f"/api/me/cases/{cid}/documents", files=_pdf())
        ).json()
        resp = await user_client.delete(
            f"/api/me/cases/{cid}/documents/{doc['id']}"
        )
        assert resp.status_code == 204
        assert (await user_client.get(f"/api/me/cases/{cid}/documents")).json() == []
        dl = await user_client.get(
            f"/api/me/cases/{cid}/documents/{doc['id']}/download"
        )
        assert dl.status_code == 404

    async def test_other_user_cannot_see_documents(
        self, user_client, make_client, sent_emails
    ):
        cid = await _case_id(user_client)
        doc = (
            await user_client.post(f"/api/me/cases/{cid}/documents", files=_pdf())
        ).json()

        other = await make_client()
        await other.post(
            "/api/leads",
            json={"name": "Other Person", "email": "other@example.com", "phone": None},
        )
        resp = await other.post(
            "/api/auth/claim",
            json={"token": claim_token_from(sent_emails), "password": "otherpass123"},
        )
        assert resp.status_code == 200

        assert (await other.get(f"/api/me/cases/{cid}/documents")).status_code == 404
        assert (
            await other.get(f"/api/me/cases/{cid}/documents/{doc['id']}/download")
        ).status_code == 404

    async def test_admin_can_list_and_download(self, user_client, admin_client):
        cid = await _case_id(user_client)
        doc = (
            await user_client.post(f"/api/me/cases/{cid}/documents", files=_pdf())
        ).json()

        listing = (await admin_client.get(f"/api/admin/cases/{cid}/documents")).json()
        assert [d["id"] for d in listing] == [doc["id"]]
        dl = await admin_client.get(
            f"/api/admin/cases/{cid}/documents/{doc['id']}/download"
        )
        assert dl.status_code == 200
        assert dl.content == PDF_BYTES

    async def test_dashboard_includes_latest_update(self, user_client, admin_client):
        cid = await _case_id(user_client)
        resp = await admin_client.post(
            f"/api/admin/cases/{cid}/updates",
            json={"body": "We requested your records."},
        )
        assert resp.status_code == 201
        cases = (await user_client.get("/api/me/cases")).json()
        mine = next(c for c in cases if c["id"] == cid)
        assert mine["latest_update_body"] == "We requested your records."
        assert mine["latest_update_at"] is not None
