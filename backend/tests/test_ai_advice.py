from tests.test_estimates import seed_ai_settings


async def _injury_type_with_question(admin_client) -> int:
    itid = (
        await admin_client.post(
            "/api/admin/injury-types", json={"name": "Slip and Fall", "is_published": True}
        )
    ).json()["id"]
    await admin_client.post(
        f"/api/admin/injury-types/{itid}/questions",
        json={
            "type": "single_choice",
            "prompt": "Where did it happen?",
            "options": [
                {"label": "Store", "value": "store"},
                {"label": "Sidewalk", "value": "sidewalk"},
            ],
        },
    )
    return itid


async def test_advice_requires_configuration(admin_client):
    itid = await _injury_type_with_question(admin_client)
    resp = await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ai_not_configured"


async def test_advice_persists_and_regenerate_overwrites(
    admin_client, session_factory, monkeypatch
):
    await seed_ai_settings(session_factory)
    itid = await _injury_type_with_question(admin_client)

    prompts: list[str] = []
    replies = iter(["First advice", "Second advice"])

    async def _fake(api_key, model, messages, json_schema=None, schema_name="response",
                    referer=None):
        prompts.append(messages[1]["content"])
        return next(replies)

    monkeypatch.setattr("app.services.openrouter.chat_completion", _fake)

    empty = await admin_client.get(f"/api/admin/ai/injury-types/{itid}/advice")
    assert empty.json() is None

    created = (await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert created["content"] == "First advice"
    assert created["model"] == "test/model"
    assert "Where did it happen?" in prompts[0]
    assert "Store | Sidewalk" in prompts[0]

    fetched = (await admin_client.get(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert fetched["content"] == "First advice"

    regenerated = (await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert regenerated["content"] == "Second advice"


async def test_advice_unknown_injury_type_404(admin_client):
    resp = await admin_client.get("/api/admin/ai/injury-types/9999/advice")
    assert resp.status_code == 404
