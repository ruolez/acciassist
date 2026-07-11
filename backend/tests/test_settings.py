SMTP_PAYLOAD = {
    "smtp_host": "mail.example.com",
    "smtp_port": 2525,
    "smtp_username": "mailer",
    "smtp_password": "secret-value",
    "smtp_tls_mode": "starttls",
    "from_email": "noreply@example.com",
    "from_name": "AcciAssist",
    "app_base_url": "https://acciassist.example",
}


async def test_settings_roundtrip_masks_password(admin_client):
    initial = (await admin_client.get("/api/admin/settings")).json()
    assert initial["smtp_host"] is None
    assert initial["smtp_password_set"] is False

    saved = (await admin_client.put("/api/admin/settings", json=SMTP_PAYLOAD)).json()
    assert saved["smtp_host"] == "mail.example.com"
    assert saved["smtp_password_set"] is True
    assert "smtp_password" not in saved

    fetched = (await admin_client.get("/api/admin/settings")).json()
    assert fetched == saved


async def test_omitted_password_kept_blank_password_clears(admin_client, sent_emails):
    await admin_client.put("/api/admin/settings", json=SMTP_PAYLOAD)

    keep = dict(SMTP_PAYLOAD, smtp_password=None)
    kept = (await admin_client.put("/api/admin/settings", json=keep)).json()
    assert kept["smtp_password_set"] is True

    resp = await admin_client.post(
        "/api/admin/settings/test-email", json={"to_email": "check@example.com"}
    )
    assert resp.status_code == 200
    snapshot, _ = sent_emails[-1]
    assert snapshot["password"] == "secret-value"

    clear = dict(SMTP_PAYLOAD, smtp_password="")
    cleared = (await admin_client.put("/api/admin/settings", json=clear)).json()
    assert cleared["smtp_password_set"] is False


async def test_test_email_unconfigured_returns_400(admin_client):
    resp = await admin_client.post(
        "/api/admin/settings/test-email", json={"to_email": "check@example.com"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "smtp_not_configured"


async def test_test_email_success_and_log(admin_client, sent_emails):
    await admin_client.put("/api/admin/settings", json=SMTP_PAYLOAD)
    resp = await admin_client.post(
        "/api/admin/settings/test-email", json={"to_email": "check@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    snapshot, msg = sent_emails[0]
    assert snapshot["host"] == "mail.example.com"
    assert msg["To"] == "check@example.com"

    log = (await admin_client.get("/api/admin/settings/email-log")).json()
    assert [(e["purpose"], e["status"]) for e in log] == [("test", "sent")]


async def test_test_email_smtp_failure_returns_502(admin_client, monkeypatch):
    await admin_client.put("/api/admin/settings", json=SMTP_PAYLOAD)

    def _boom(snapshot, msg):
        raise OSError("connection refused")

    monkeypatch.setattr("app.services.email._send_via_smtp", _boom)
    resp = await admin_client.post(
        "/api/admin/settings/test-email", json={"to_email": "check@example.com"}
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "smtp_send_failed"

    log = (await admin_client.get("/api/admin/settings/email-log")).json()
    assert [(e["status"], e["error"]) for e in log] == [("failed", "connection refused")]
