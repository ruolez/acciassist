from tests.conftest import ADMIN_EMAIL


class TestAdminAuth:
    async def test_unauthenticated_admin_call_returns_401(self, client):
        resp = await client.get("/api/admin/injury-types")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthenticated"

    async def test_login_with_bad_password_returns_401(self, client, admin_client):
        # admin_client fixture already created the admin; use a fresh login attempt
        resp = await client.post(
            "/api/admin/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_credentials"

    async def test_login_then_me_returns_current_admin(self, admin_client):
        resp = await admin_client.get("/api/admin/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == ADMIN_EMAIL

    async def test_logout_clears_session(self, admin_client):
        await admin_client.post("/api/admin/logout")
        admin_client.cookies.clear()
        resp = await admin_client.get("/api/admin/me")
        assert resp.status_code == 401

    async def test_admin_cannot_delete_self(self, admin_client):
        me = (await admin_client.get("/api/admin/me")).json()
        resp = await admin_client.delete(f"/api/admin/admins/{me['id']}")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "cannot_delete_self"

    async def test_create_admin_then_listed(self, admin_client):
        created = await admin_client.post(
            "/api/admin/admins", json={"email": "new@example.com", "password": "password123"}
        )
        assert created.status_code == 201
        emails = {a["email"] for a in (await admin_client.get("/api/admin/admins")).json()}
        assert emails == {ADMIN_EMAIL, "new@example.com"}

    async def test_create_duplicate_admin_returns_409(self, admin_client):
        resp = await admin_client.post(
            "/api/admin/admins", json={"email": ADMIN_EMAIL, "password": "password123"}
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "email_taken"
