import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.models import AuthToken
from tests.conftest import USER_EMAIL, USER_PASSWORD, claim_token_from, seed_smtp_settings

LEAD = {"name": "Pat Smith", "email": USER_EMAIL, "phone": "555-1234"}


async def _lead_with_token(client, session_factory, sent_emails) -> str:
    await seed_smtp_settings(session_factory)
    resp = await client.post("/api/leads", json=LEAD)
    assert resp.status_code == 201
    return claim_token_from(sent_emails)


class TestClaim:
    async def test_verify_then_claim_logs_in(self, client, session_factory, sent_emails):
        token = await _lead_with_token(client, session_factory, sent_emails)

        verify = await client.post("/api/auth/claim/verify", json={"token": token})
        assert verify.status_code == 200
        assert verify.json() == {"email": USER_EMAIL, "name": "Pat Smith"}

        claim = await client.post(
            "/api/auth/claim", json={"token": token, "password": USER_PASSWORD}
        )
        assert claim.status_code == 200
        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == USER_EMAIL

    async def test_claim_token_is_single_use(self, client, session_factory, sent_emails):
        token = await _lead_with_token(client, session_factory, sent_emails)
        first = await client.post(
            "/api/auth/claim", json={"token": token, "password": USER_PASSWORD}
        )
        assert first.status_code == 200
        second = await client.post(
            "/api/auth/claim", json={"token": token, "password": "another-pass1"}
        )
        assert second.status_code == 400
        assert second.json()["error"]["code"] == "token_used"

    async def test_expired_token_rejected_with_distinct_code(
        self, client, session_factory, sent_emails
    ):
        token = await _lead_with_token(client, session_factory, sent_emails)
        async with session_factory() as s:
            await s.execute(
                update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
            )
            await s.commit()
        resp = await client.post("/api/auth/claim/verify", json={"token": token})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "token_expired"

    async def test_garbage_token_rejected(self, client):
        resp = await client.post("/api/auth/claim/verify", json={"token": "garbage"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_token"

    async def test_resend_invalidates_old_token_and_never_enumerates(
        self, client, session_factory, sent_emails
    ):
        old_token = await _lead_with_token(client, session_factory, sent_emails)

        resp = await client.post("/api/auth/claim/resend", json={"email": USER_EMAIL})
        assert resp.status_code == 200 and resp.json() == {"ok": True}
        new_token = claim_token_from(sent_emails)
        assert new_token != old_token

        stale = await client.post("/api/auth/claim/verify", json={"token": old_token})
        assert stale.json()["error"]["code"] == "token_used"
        fresh = await client.post("/api/auth/claim/verify", json={"token": new_token})
        assert fresh.status_code == 200

        unknown = await client.post(
            "/api/auth/claim/resend", json={"email": "nobody@example.com"}
        )
        assert unknown.status_code == 200 and unknown.json() == {"ok": True}


class TestLogin:
    async def test_unclaimed_user_cannot_log_in(self, client, session_factory, sent_emails):
        await _lead_with_token(client, session_factory, sent_emails)
        resp = await client.post(
            "/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_credentials"

    async def test_login_logout_cycle(self, user_client):
        await user_client.post("/api/auth/logout")
        assert (await user_client.get("/api/auth/me")).status_code == 401
        resp = await user_client.post(
            "/api/auth/login", json={"email": USER_EMAIL.upper(), "password": USER_PASSWORD}
        )
        assert resp.status_code == 200
        assert (await user_client.get("/api/auth/me")).status_code == 200


class TestPasswordReset:
    async def test_forgot_and_reset_flow(self, user_client, sent_emails):
        resp = await user_client.post(
            "/api/auth/forgot-password", json={"email": USER_EMAIL}
        )
        assert resp.status_code == 200 and resp.json() == {"ok": True}
        body = sent_emails[-1][1].get_body(preferencelist=("plain",)).get_content()
        token = re.search(r"reset-password\?token=([A-Za-z0-9_-]+)", body).group(1)

        reset = await user_client.post(
            "/api/auth/reset-password", json={"token": token, "password": "new-pass-123"}
        )
        assert reset.status_code == 200

        again = await user_client.post(
            "/api/auth/reset-password", json={"token": token, "password": "sneaky-pass1"}
        )
        assert again.json()["error"]["code"] == "token_used"

        await user_client.post("/api/auth/logout")
        old = await user_client.post(
            "/api/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        assert old.status_code == 401
        new = await user_client.post(
            "/api/auth/login", json={"email": USER_EMAIL, "password": "new-pass-123"}
        )
        assert new.status_code == 200

    async def test_forgot_password_ignores_unknown_and_unclaimed(
        self, client, session_factory, sent_emails
    ):
        await _lead_with_token(client, session_factory, sent_emails)
        emails_before = len(sent_emails)
        for email in (USER_EMAIL, "nobody@example.com"):
            resp = await client.post("/api/auth/forgot-password", json={"email": email})
            assert resp.status_code == 200 and resp.json() == {"ok": True}
        assert len(sent_emails) == emails_before

    async def test_reset_token_hidden_from_claim_endpoint(self, user_client, sent_emails):
        await user_client.post("/api/auth/forgot-password", json={"email": USER_EMAIL})
        body = sent_emails[-1][1].get_body(preferencelist=("plain",)).get_content()
        token = re.search(r"reset-password\?token=([A-Za-z0-9_-]+)", body).group(1)
        resp = await user_client.post("/api/auth/claim/verify", json={"token": token})
        assert resp.json()["error"]["code"] == "invalid_token"


class TestScopeIsolation:
    async def test_admin_cookie_rejected_on_user_endpoints(self, admin_client):
        resp = await admin_client.get("/api/auth/me")
        assert resp.status_code == 401

    async def test_user_cookie_rejected_on_admin_endpoints(self, user_client):
        resp = await user_client.get("/api/admin/me")
        assert resp.status_code == 401
        resp = await user_client.get("/api/admin/leads")
        assert resp.status_code == 401
