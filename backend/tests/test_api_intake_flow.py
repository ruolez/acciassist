async def _create_published_injury_type(admin_client, name="Auto Accident"):
    resp = await admin_client.post(
        "/api/admin/injury-types", json={"name": name, "is_published": True}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _add_question(admin_client, injury_type_id, **payload):
    resp = await admin_client.post(
        f"/api/admin/injury-types/{injury_type_id}/questions", json=payload
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestContentManagement:
    async def test_created_injury_type_gets_slug(self, admin_client):
        resp = await admin_client.post(
            "/api/admin/injury-types", json={"name": "Slip and Fall", "is_published": False}
        )
        assert resp.json()["slug"] == "slip-and-fall"

    async def test_question_reorder_updates_display_order(self, admin_client):
        itid = await _create_published_injury_type(admin_client)
        q1 = await _add_question(
            admin_client, itid, type="yes_no", prompt="First?", is_required=True
        )
        q2 = await _add_question(
            admin_client, itid, type="yes_no", prompt="Second?", is_required=True
        )
        resp = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions/reorder",
            json={"ordered_ids": [q2["id"], q1["id"]]},
        )
        assert resp.status_code == 204
        questions = (
            await admin_client.get(f"/api/admin/injury-types/{itid}/questions")
        ).json()
        assert [q["id"] for q in questions] == [q2["id"], q1["id"]]

    async def test_reorder_with_mismatched_ids_returns_400(self, admin_client):
        itid = await _create_published_injury_type(admin_client)
        q1 = await _add_question(admin_client, itid, type="yes_no", prompt="Only?")
        resp = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions/reorder",
            json={"ordered_ids": [q1["id"], 9999]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_reorder"


class TestPublicIntakeFlow:
    async def test_unpublished_injury_type_hidden_from_public(self, admin_client):
        await admin_client.post(
            "/api/admin/injury-types", json={"name": "Hidden", "is_published": False}
        )
        public = (await admin_client.get("/api/injury-types")).json()
        assert public == []

    async def test_full_flow_renders_summary_with_answers(self, admin_client):
        itid = await _create_published_injury_type(admin_client)
        role = await _add_question(
            admin_client,
            itid,
            type="single_choice",
            prompt="Driver or passenger?",
            options=[
                {"label": "Driver", "value": "driver"},
                {"label": "Passenger", "value": "passenger"},
            ],
        )
        story = await _add_question(
            admin_client, itid, type="long_text", prompt="What happened?"
        )
        await admin_client.put(
            f"/api/admin/injury-types/{itid}/summary-template",
            json={
                "body": "Role: {{driver-or-passenger}} | Story: {{what-happened}}",
                "estimate_min": 1000,
                "estimate_max": 9000,
            },
        )

        start = (
            await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
        ).json()
        assert start["total_pages"] == 2  # two ungrouped questions -> two pages
        sid = start["session_id"]

        save = await admin_client.post(
            f"/api/intake/{sid}/answers",
            json={
                "answers": [
                    {"question_id": role["id"], "value": "driver"},
                    {"question_id": story["id"], "value": "Rear-ended at a light."},
                ]
            },
        )
        assert save.status_code == 204

        summary = (await admin_client.post(f"/api/intake/{sid}/complete")).json()
        assert summary["body"] == "Role: Driver | Story: Rear-ended at a light."
        assert (summary["estimate_min"], summary["estimate_max"]) == (1000, 9000)

    async def test_answers_are_idempotent_on_resave(self, admin_client):
        itid = await _create_published_injury_type(admin_client)
        q = await _add_question(admin_client, itid, type="short_text", prompt="Name?")
        start = (
            await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
        ).json()
        sid = start["session_id"]
        for value in ("Pat", "Patricia"):
            await admin_client.post(
                f"/api/intake/{sid}/answers",
                json={"answers": [{"question_id": q["id"], "value": value}]},
            )
        detail = (
            await admin_client.get(f"/api/admin/intake-sessions/{sid}")
        ).json()
        assert detail["answers"] == [{"question_id": q["id"], "value": "Patricia"}]

    async def test_session_pages_reflect_questions_added_after_start(self, admin_client):
        itid = await _create_published_injury_type(admin_client)
        await _add_question(admin_client, itid, type="yes_no", prompt="Original?")
        start = (
            await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
        ).json()
        await _add_question(admin_client, itid, type="number", prompt="Added later?")

        fresh = (
            await admin_client.get(f"/api/intake/{start['session_id']}/pages")
        ).json()
        assert fresh["session_id"] == start["session_id"]
        assert fresh["total_pages"] == 2
        prompts = [q["prompt"] for p in fresh["pages"] for q in p["questions"]]
        assert prompts == ["Original?", "Added later?"]

    async def test_session_pages_unknown_session_404(self, admin_client):
        resp = await admin_client.get(
            "/api/intake/00000000-0000-0000-0000-000000000000/pages"
        )
        assert resp.status_code == 404

    async def test_lead_capture_appears_in_admin_list(self, admin_client):
        itid = await _create_published_injury_type(admin_client)
        start = (
            await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
        ).json()
        created = await admin_client.post(
            "/api/leads",
            json={
                "intake_session_id": start["session_id"],
                "name": "Pat Smith",
                "email": "pat@example.com",
                "phone": "555-1234",
            },
        )
        assert created.status_code == 201
        leads = (await admin_client.get("/api/admin/leads")).json()
        assert [(lead["name"], lead["email"]) for lead in leads] == [
            ("Pat Smith", "pat@example.com")
        ]
