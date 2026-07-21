import json

from tests.test_estimates import seed_ai_settings


def advice_reply(overview="Coverage looks thin.", new_questions=None, question_edits=None):
    return json.dumps(
        {
            "overview": overview,
            "new_questions": new_questions or [],
            "question_edits": question_edits or [],
        }
    )


NEW_QUESTION = {
    "type": "number",
    "prompt": "How much were your medical bills so far?",
    "help_text": None,
    "is_required": True,
    "config": {"placeholder": None, "min": 0, "max": None, "max_length": None,
               "disallow_future": None},
    "options": [],
    "rationale": "Medical specials anchor the payout estimate.",
}


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

    calls: list[dict] = []
    replies = iter(
        [advice_reply("First overview", [NEW_QUESTION]), advice_reply("Second overview")]
    )

    async def _fake(api_key, model, messages, json_schema=None, schema_name="response",
                    referer=None, **kwargs):
        calls.append({"messages": messages, "json_schema": json_schema})
        return next(replies)

    monkeypatch.setattr("app.services.openrouter.chat_completion", _fake)

    empty = await admin_client.get(f"/api/admin/ai/injury-types/{itid}/advice")
    assert empty.json() is None

    created = (await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert created["content"] == "First overview"
    assert created["model"] == "test/model"
    assert [p["kind"] for p in created["proposals"]] == ["add"]
    assert created["proposals"][0]["payload"]["prompt"] == NEW_QUESTION["prompt"]
    assert created["proposals"][0]["applied"] is False

    assert calls[0]["json_schema"] is not None
    user_message = calls[0]["messages"][1]["content"]
    assert "Where did it happen?" in user_message
    assert '"id"' in user_message

    fetched = (await admin_client.get(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert fetched == created

    regenerated = (await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert regenerated["content"] == "Second overview"
    assert regenerated["proposals"] == []


async def test_think_block_reply_parses(admin_client, session_factory, monkeypatch):
    """Reasoning models (Qwen, DeepSeek) prepend <think> blocks whose braces
    must not corrupt JSON extraction."""
    await seed_ai_settings(session_factory)
    itid = await _injury_type_with_question(admin_client)

    async def _thinking(*args, **kwargs):
        return (
            "<think>The user wants {json}. Let me consider {a: 1} carefully.</think>\n"
            + advice_reply("Thought-through overview", [NEW_QUESTION])
        )

    monkeypatch.setattr("app.services.openrouter.chat_completion", _thinking)
    created = (await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert created["content"] == "Thought-through overview"
    assert len(created["proposals"]) == 1


async def test_fenced_reply_parses(admin_client, session_factory, monkeypatch):
    await seed_ai_settings(session_factory)
    itid = await _injury_type_with_question(admin_client)

    async def _fenced(*args, **kwargs):
        return f"```json\n{advice_reply('Fenced overview')}\n```"

    monkeypatch.setattr("app.services.openrouter.chat_completion", _fenced)
    created = (await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert created["content"] == "Fenced overview"


async def test_unparseable_reply_returns_502(admin_client, session_factory, monkeypatch):
    await seed_ai_settings(session_factory)
    itid = await _injury_type_with_question(admin_client)

    async def _garbage(*args, **kwargs):
        return "I am unable to produce JSON today."

    monkeypatch.setattr("app.services.openrouter.chat_completion", _garbage)
    resp = await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "ai_invalid_response"


async def test_advice_unknown_injury_type_404(admin_client):
    resp = await admin_client.get("/api/admin/ai/injury-types/9999/advice")
    assert resp.status_code == 404


async def test_legacy_advice_row_without_proposals(admin_client, session_factory):
    from app.models import EstimateAdvice

    itid = await _injury_type_with_question(admin_client)
    async with session_factory() as s:
        s.add(EstimateAdvice(injury_type_id=itid, content="Old prose advice"))
        await s.commit()
    fetched = (await admin_client.get(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert fetched["content"] == "Old prose advice"
    assert fetched["proposals"] is None
