from sqlalchemy import select

from app.models import AuthToken, Case, CaseStage, TokenPurpose, User
from app.security import hash_password
from tests.test_settings import SMTP_PAYLOAD

LEAD = {"name": "Pat Smith", "email": "Pat@Example.com", "phone": "555-1234"}


def _plain_body(msg) -> str:
    return msg.get_body(preferencelist=("plain",)).get_content()


async def _published_intake(admin_client, estimate=(5000, 25000)):
    resp = await admin_client.post(
        "/api/admin/injury-types", json={"name": "Auto Accident", "is_published": True}
    )
    itid = resp.json()["id"]
    await admin_client.put(
        f"/api/admin/injury-types/{itid}/summary-template",
        json={"body": "Summary", "estimate_min": estimate[0], "estimate_max": estimate[1]},
    )
    start = (
        await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
    ).json()
    return start["session_id"]


async def _submit_lead(client, session_id=None, **overrides):
    payload = {**LEAD, "intake_session_id": session_id, **overrides}
    resp = await client.post("/api/leads", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_lead_creates_user_case_and_claim_email(
    admin_client, session_factory, sent_emails
):
    await admin_client.put("/api/admin/settings", json=SMTP_PAYLOAD)
    sid = await _published_intake(admin_client)
    lead = await _submit_lead(admin_client, sid)

    async with session_factory() as s:
        user = await s.scalar(select(User).where(User.email == "pat@example.com"))
        assert user is not None and user.password_hash is None
        case = await s.scalar(select(Case).where(Case.lead_id == lead["id"]))
        assert case is not None
        assert (case.user_id, case.stage) == (user.id, CaseStage.new)
        token = await s.scalar(select(AuthToken).where(AuthToken.user_id == user.id))
        assert (token.purpose, token.used_at) == (TokenPurpose.account_claim, None)

    assert len(sent_emails) == 1
    _, msg = sent_emails[0]
    assert msg["To"] == "pat@example.com"
    body = _plain_body(msg)
    assert "$5,000 – $25,000" in body
    assert "https://acciassist.example/account/claim?token=" in body


async def test_second_lead_same_email_reuses_user_and_reissues_token(
    admin_client, session_factory, sent_emails
):
    await admin_client.put("/api/admin/settings", json=SMTP_PAYLOAD)
    first = await _submit_lead(admin_client)
    second = await _submit_lead(admin_client, email="PAT@example.com")
    assert first["id"] != second["id"]

    async with session_factory() as s:
        users = list(await s.scalars(select(User)))
        assert len(users) == 1
        cases = list(await s.scalars(select(Case).order_by(Case.id)))
        assert [c.lead_id for c in cases] == [first["id"], second["id"]]
        tokens = list(await s.scalars(select(AuthToken).order_by(AuthToken.id)))
        assert [t.used_at is None for t in tokens] == [False, True]

    assert len(sent_emails) == 2
    assert "claim?token=" in _plain_body(sent_emails[1][1])


async def test_claimed_user_gets_login_variant(admin_client, session_factory, sent_emails):
    await admin_client.put("/api/admin/settings", json=SMTP_PAYLOAD)
    async with session_factory() as s:
        s.add(
            User(
                email="pat@example.com",
                name="Pat Smith",
                password_hash=hash_password("password123"),
            )
        )
        await s.commit()

    await _submit_lead(admin_client)
    assert len(sent_emails) == 1
    body = _plain_body(sent_emails[0][1])
    assert "claim?token=" not in body
    assert "https://acciassist.example/login" in body

    async with session_factory() as s:
        tokens = list(await s.scalars(select(AuthToken)))
        assert tokens == []


async def test_lead_succeeds_when_smtp_unconfigured(admin_client, sent_emails):
    await _submit_lead(admin_client)
    assert sent_emails == []
    log = (await admin_client.get("/api/admin/settings/email-log")).json()
    assert [(e["purpose"], e["status"]) for e in log] == [("lead_received", "skipped")]


async def test_lead_succeeds_when_smtp_fails(admin_client, monkeypatch):
    await admin_client.put("/api/admin/settings", json=SMTP_PAYLOAD)

    def _boom(snapshot, msg):
        raise OSError("connection refused")

    monkeypatch.setattr("app.services.email._send_via_smtp", _boom)
    await _submit_lead(admin_client)
    log = (await admin_client.get("/api/admin/settings/email-log")).json()
    assert [(e["purpose"], e["status"]) for e in log] == [("lead_received", "failed")]