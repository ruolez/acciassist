from tests.conftest import claim_token_from, seed_smtp_settings


async def _full_intake_lead(admin_client, client, email: str, name: str = "Pat Smith"):
    """Published injury type + completed intake + lead; returns the case id."""
    resp = await admin_client.post(
        "/api/admin/injury-types", json={"name": "Auto Accident", "is_published": True}
    )
    itid = resp.json()["id"]
    q = await admin_client.post(
        f"/api/admin/injury-types/{itid}/questions",
        json={"type": "short_text", "prompt": "What happened?"},
    )
    await admin_client.put(
        f"/api/admin/injury-types/{itid}/summary-template",
        json={"body": "Story: {{what-happened}}", "estimate_min": 5000, "estimate_max": 25000},
    )
    start = (await client.post("/api/intake/start", json={"injury_type_id": itid})).json()
    sid = start["session_id"]
    await client.post(
        f"/api/intake/{sid}/answers",
        json={"answers": [{"question_id": q.json()["id"], "value": "Rear-ended."}]},
    )
    await client.post(f"/api/intake/{sid}/complete")
    lead = await client.post(
        "/api/leads",
        json={"intake_session_id": sid, "name": name, "email": email, "phone": "555-1234"},
    )
    assert lead.status_code == 201
    cases = (await admin_client.get("/api/admin/cases")).json()
    return cases[0]["id"]


async def _claimed_client(make_client, sent_emails, email: str, password: str = "userpass123"):
    c = await make_client()
    await c.post("/api/leads", json={"name": "Someone Else", "email": email, "phone": None})
    resp = await c.post(
        "/api/auth/claim", json={"token": claim_token_from(sent_emails), "password": password}
    )
    assert resp.status_code == 200
    return c


class TestUserPortal:
    async def test_dashboard_lists_case_with_context(
        self, admin_client, user_client, session_factory
    ):
        # user_client already created one bare lead; add a full-intake case too.
        await _full_intake_lead(admin_client, user_client, "pat@example.com")
        cases = (await user_client.get("/api/me/cases")).json()
        assert len(cases) == 2
        newest = cases[0]
        assert newest["injury_type_name"] == "Auto Accident"
        assert (newest["estimate_min"], newest["estimate_max"]) == (5000, 25000)
        assert newest["stage"] == "new"

    async def test_case_detail_includes_summary_and_contact(
        self, admin_client, user_client
    ):
        await _full_intake_lead(admin_client, user_client, "pat@example.com")
        cases = (await user_client.get("/api/me/cases")).json()
        detail = (await user_client.get(f"/api/me/cases/{cases[0]['id']}")).json()
        assert detail["summary"]["body"] == "Story: Rear-ended."
        assert detail["email"] == "pat@example.com"
        assert detail["updates"] == []

    async def test_cannot_see_other_users_case(
        self, admin_client, user_client, make_client, session_factory, sent_emails
    ):
        other = await _claimed_client(make_client, sent_emails, "other@example.com")
        case_id = (await user_client.get("/api/me/cases")).json()[0]["id"]
        resp = await other.get(f"/api/me/cases/{case_id}")
        assert resp.status_code == 404

    async def test_profile_update(self, user_client):
        resp = await user_client.patch(
            "/api/me/profile", json={"name": "Pat S. Smith", "phone": "555-9999"}
        )
        assert resp.status_code == 200
        me = (await user_client.get("/api/auth/me")).json()
        assert (me["name"], me["phone"]) == ("Pat S. Smith", "555-9999")


class TestAdminCases:
    async def test_stage_change_creates_feed_entry_and_email(
        self, admin_client, user_client, sent_emails
    ):
        case_id = (await user_client.get("/api/me/cases")).json()[0]["id"]
        emails_before = len(sent_emails)

        resp = await admin_client.patch(
            f"/api/admin/cases/{case_id}", json={"stage": "under_review"}
        )
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["stage"] == "under_review"
        assert [(u["kind"], u["body"]) for u in detail["updates"]] == [
            ("stage_change", "Stage changed to Under review")
        ]
        assert len(sent_emails) == emails_before + 1
        assert "Under review" in str(sent_emails[-1][1])

        user_view = (await user_client.get(f"/api/me/cases/{case_id}")).json()
        assert user_view["stage"] == "under_review"
        assert user_view["updates"][0]["kind"] == "stage_change"
        assert "admin_email" not in user_view["updates"][0]

    async def test_same_stage_patch_is_noop(self, admin_client, user_client, sent_emails):
        case_id = (await user_client.get("/api/me/cases")).json()[0]["id"]
        emails_before = len(sent_emails)
        resp = await admin_client.patch(f"/api/admin/cases/{case_id}", json={"stage": "new"})
        assert resp.status_code == 200
        assert resp.json()["updates"] == []
        assert len(sent_emails) == emails_before

    async def test_posting_update_notifies_user(self, admin_client, user_client, sent_emails):
        case_id = (await user_client.get("/api/me/cases")).json()[0]["id"]
        resp = await admin_client.post(
            f"/api/admin/cases/{case_id}/updates",
            json={"body": "We requested your medical records."},
        )
        assert resp.status_code == 201
        assert resp.json()["updates"][0]["body"] == "We requested your medical records."
        assert resp.json()["updates"][0]["admin_email"] == "tester@example.com"

        body = str(sent_emails[-1][1])
        assert "new update" in body.lower()
        assert "medical records" not in body  # content stays behind login

    async def test_stage_filter(self, admin_client, user_client):
        case_id = (await user_client.get("/api/me/cases")).json()[0]["id"]
        await admin_client.patch(f"/api/admin/cases/{case_id}", json={"stage": "negotiating"})
        negotiating = (await admin_client.get("/api/admin/cases?stage=negotiating")).json()
        assert [c["id"] for c in negotiating] == [case_id]
        assert (await admin_client.get("/api/admin/cases?stage=settled")).json() == []

    async def test_resend_invite_only_for_unclaimed(
        self, admin_client, client, session_factory, sent_emails
    ):
        await seed_smtp_settings(session_factory)
        resp = await client.post(
            "/api/leads", json={"name": "New Person", "email": "new@example.com", "phone": None}
        )
        assert resp.status_code == 201
        case_id = (await admin_client.get("/api/admin/cases")).json()[0]["id"]

        old_token = claim_token_from(sent_emails)
        resend = await admin_client.post(f"/api/admin/cases/{case_id}/resend-invite")
        assert resend.status_code == 200
        new_token = claim_token_from(sent_emails)
        assert new_token != old_token

        claim = await client.post(
            "/api/auth/claim", json={"token": new_token, "password": "userpass123"}
        )
        assert claim.status_code == 200

        again = await admin_client.post(f"/api/admin/cases/{case_id}/resend-invite")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "already_claimed"
