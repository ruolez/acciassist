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


class TestDocumentLabels:
    async def test_upload_with_admin_defined_label(self, user_client, admin_client):
        created = await admin_client.post(
            "/api/admin/document-types", json={"name": "Medical bill"}
        )
        assert created.status_code == 201

        cid = await _case_id(user_client)
        resp = await user_client.post(
            f"/api/me/cases/{cid}/documents",
            files=_pdf(),
            data={"label": "Medical bill"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["label"] == "Medical bill"
        listing = (await user_client.get(f"/api/me/cases/{cid}/documents")).json()
        assert listing[0]["label"] == "Medical bill"

    async def test_label_is_optional(self, user_client):
        cid = await _case_id(user_client)
        resp = await user_client.post(f"/api/me/cases/{cid}/documents", files=_pdf())
        assert resp.status_code == 201
        assert resp.json()["label"] is None

    async def test_rejects_label_not_in_document_types(self, user_client):
        cid = await _case_id(user_client)
        resp = await user_client.post(
            f"/api/me/cases/{cid}/documents",
            files=_pdf(),
            data={"label": "Tax return"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_label"

    async def test_patient_lists_types_in_admin_order(self, user_client, admin_client):
        ids = []
        for name in ["Photo", "Medical bill", "Other"]:
            resp = await admin_client.post(
                "/api/admin/document-types", json={"name": name}
            )
            ids.append(resp.json()["id"])
        await admin_client.post(
            "/api/admin/document-types/reorder",
            json={"ordered_ids": [ids[1], ids[0], ids[2]]},
        )
        listing = (await user_client.get("/api/me/document-types")).json()
        assert [t["name"] for t in listing] == ["Medical bill", "Photo", "Other"]

    async def test_admin_rejects_duplicate_type(self, admin_client):
        first = await admin_client.post(
            "/api/admin/document-types", json={"name": "Photo"}
        )
        assert first.status_code == 201
        dup = await admin_client.post(
            "/api/admin/document-types", json={"name": "photo"}
        )
        assert dup.status_code == 409

    async def test_admin_deletes_type_but_labels_survive(
        self, user_client, admin_client
    ):
        created = (
            await admin_client.post(
                "/api/admin/document-types", json={"name": "Photo"}
            )
        ).json()
        cid = await _case_id(user_client)
        doc = (
            await user_client.post(
                f"/api/me/cases/{cid}/documents", files=_pdf(), data={"label": "Photo"}
            )
        ).json()
        resp = await admin_client.delete(f"/api/admin/document-types/{created['id']}")
        assert resp.status_code == 204
        listing = (await user_client.get(f"/api/me/cases/{cid}/documents")).json()
        assert listing[0]["id"] == doc["id"]
        assert listing[0]["label"] == "Photo"


class TestUpdateReadState:
    async def test_updates_start_unread_and_mark_read(self, user_client, admin_client):
        cid = await _case_id(user_client)
        resp = await admin_client.post(
            f"/api/admin/cases/{cid}/updates",
            json={"body": "We requested your records."},
        )
        assert resp.status_code == 201

        detail = (await user_client.get(f"/api/me/cases/{cid}")).json()
        assert [u["read_at"] for u in detail["updates"]] == [None]

        resp = await user_client.post(f"/api/me/cases/{cid}/updates/mark-read")
        assert resp.status_code == 204

        detail = (await user_client.get(f"/api/me/cases/{cid}")).json()
        assert all(u["read_at"] is not None for u in detail["updates"])

    async def test_mark_single_update_read(self, user_client, admin_client):
        cid = await _case_id(user_client)
        for body in ["First update.", "Second update."]:
            await admin_client.post(
                f"/api/admin/cases/{cid}/updates", json={"body": body}
            )
        detail = (await user_client.get(f"/api/me/cases/{cid}")).json()
        first_id = detail["updates"][0]["id"]

        resp = await user_client.post(
            f"/api/me/cases/{cid}/updates/{first_id}/read"
        )
        assert resp.status_code == 204

        detail = (await user_client.get(f"/api/me/cases/{cid}")).json()
        by_id = {u["id"]: u["read_at"] for u in detail["updates"]}
        assert by_id[first_id] is not None
        assert sum(1 for v in by_id.values() if v is None) == 1

        missing = await user_client.post(f"/api/me/cases/{cid}/updates/999999/read")
        assert missing.status_code == 404

    async def test_mark_read_requires_case_ownership(
        self, user_client, admin_client, make_client, sent_emails
    ):
        cid = await _case_id(user_client)
        other = await make_client()
        await other.post(
            "/api/leads",
            json={"name": "Other Person", "email": "other2@example.com", "phone": None},
        )
        resp = await other.post(
            "/api/auth/claim",
            json={"token": claim_token_from(sent_emails), "password": "otherpass123"},
        )
        assert resp.status_code == 200
        resp = await other.post(f"/api/me/cases/{cid}/updates/mark-read")
        assert resp.status_code == 404
