import json

import pytest

from app.services.estimates import parse_estimate_content
from app.services.openrouter import OpenRouterError

VALID_ESTIMATE = {
    "payout_min": 5000,
    "payout_max": 20000,
    "case_cost_min": 1000,
    "case_cost_max": 3000,
    "confidence": "medium",
    "reasoning": "Rear-end collision with clear liability but unknown treatment.",
    "missing_information": ["medical treatment details"],
}


async def seed_ai_settings(session_factory) -> None:
    from app.services.email import get_app_settings

    async with session_factory() as s:
        row = await get_app_settings(s)
        row.openrouter_api_key = "sk-or-test"
        row.openrouter_model = "test/model"
        await s.commit()


@pytest.fixture
def ai_calls(monkeypatch):
    """Capture chat_completion calls; each entry is the kwargs of one call."""
    calls: list[dict] = []

    async def _fake(api_key, model, messages, json_schema=None, schema_name="response",
                    referer=None):
        calls.append({"api_key": api_key, "model": model, "messages": messages,
                      "json_schema": json_schema})
        return json.dumps(VALID_ESTIMATE)

    monkeypatch.setattr("app.services.openrouter.chat_completion", _fake)
    return calls


async def _completed_session(admin_client) -> str:
    resp = await admin_client.post(
        "/api/admin/injury-types", json={"name": "Auto Accident", "is_published": True}
    )
    itid = resp.json()["id"]
    q = (
        await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "yes_no", "prompt": "Were you injured?"},
        )
    ).json()
    sid = (
        await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
    ).json()["session_id"]
    await admin_client.post(
        f"/api/intake/{sid}/answers",
        json={"answers": [{"question_id": q["id"], "value": True}]},
    )
    resp = await admin_client.post(f"/api/intake/{sid}/complete")
    assert resp.status_code == 200
    return sid


class TestParseEstimateContent:
    def test_plain_json(self):
        result = parse_estimate_content(json.dumps(VALID_ESTIMATE))
        assert result.payout_min == 5000
        assert result.confidence == "medium"

    def test_fenced_json_with_prose(self):
        content = f"Here is my estimate:\n```json\n{json.dumps(VALID_ESTIMATE)}\n```"
        assert parse_estimate_content(content).payout_max == 20000

    def test_inverted_range_is_swapped_and_negatives_clamped(self):
        payload = dict(VALID_ESTIMATE, payout_min=20000, payout_max=5000, case_cost_min=-50)
        result = parse_estimate_content(json.dumps(payload))
        assert (result.payout_min, result.payout_max) == (5000, 20000)
        assert result.case_cost_min == 0

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            parse_estimate_content("I cannot provide an estimate.")


async def test_unconfigured_completion_creates_no_estimate(admin_client):
    sid = await _completed_session(admin_client)
    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body == {"status": "none", "payout_min": None, "payout_max": None}


async def test_configured_completion_produces_estimate(admin_client, session_factory, ai_calls):
    await seed_ai_settings(session_factory)
    sid = await _completed_session(admin_client)

    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body == {"status": "completed", "payout_min": 5000, "payout_max": 20000}

    assert len(ai_calls) == 1
    assert ai_calls[0]["model"] == "test/model"
    assert ai_calls[0]["json_schema"] is not None
    assert "Were you injured?: Yes" in ai_calls[0]["messages"][1]["content"]

    admin_body = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
    assert admin_body["status"] == "completed"
    assert admin_body["case_cost_min"] == 1000
    assert admin_body["reasoning"] == VALID_ESTIMATE["reasoning"]
    assert admin_body["missing_info"] == ["medical treatment details"]
    assert admin_body["model"] == "test/model"


async def test_public_estimate_never_leaks_admin_fields(
    admin_client, session_factory, ai_calls
):
    await seed_ai_settings(session_factory)
    sid = await _completed_session(admin_client)
    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert set(body) == {"status", "payout_min", "payout_max"}


async def test_model_failure_marks_estimate_failed(admin_client, session_factory, monkeypatch):
    await seed_ai_settings(session_factory)

    async def _boom(*args, **kwargs):
        raise OpenRouterError("timeout", "The AI model did not respond in time")

    monkeypatch.setattr("app.services.openrouter.chat_completion", _boom)
    sid = await _completed_session(admin_client)

    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body == {"status": "failed", "payout_min": None, "payout_max": None}
    admin_body = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
    assert admin_body["error"] == "The AI model did not respond in time"


async def test_invalid_model_output_marks_estimate_failed(
    admin_client, session_factory, monkeypatch
):
    await seed_ai_settings(session_factory)

    async def _nonsense(*args, **kwargs):
        return "Sorry, I cannot help with that."

    monkeypatch.setattr("app.services.openrouter.chat_completion", _nonsense)
    sid = await _completed_session(admin_client)
    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body["status"] == "failed"


async def test_recompleting_does_not_rerun_estimate(admin_client, session_factory, ai_calls):
    await seed_ai_settings(session_factory)
    sid = await _completed_session(admin_client)
    resp = await admin_client.post(f"/api/intake/{sid}/complete")
    assert resp.status_code == 200
    assert len(ai_calls) == 1
    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body["status"] == "completed"


async def test_rerun_requires_configuration_and_completed_session(admin_client):
    sid = await _completed_session(admin_client)
    resp = await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/rerun")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ai_not_configured"


async def test_rerun_regenerates_estimate(admin_client, session_factory, ai_calls):
    await seed_ai_settings(session_factory)
    sid = await _completed_session(admin_client)
    resp = await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/rerun")
    assert resp.status_code == 200
    assert len(ai_calls) == 2
    body = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
    assert body["status"] == "completed"


async def test_case_detail_includes_estimate(admin_client, session_factory, ai_calls):
    await seed_ai_settings(session_factory)
    sid = await _completed_session(admin_client)
    resp = await admin_client.post(
        "/api/leads",
        json={"intake_session_id": sid, "name": "Pat Smith", "email": "pat@example.com"},
    )
    assert resp.status_code == 201
    cases = (await admin_client.get("/api/admin/cases")).json()
    detail = (await admin_client.get(f"/api/admin/cases/{cases[0]['id']}")).json()
    assert detail["estimate"]["status"] == "completed"
    assert detail["estimate"]["payout_max"] == 20000

    submission = (await admin_client.get(f"/api/admin/intake-sessions/{sid}")).json()
    assert submission["estimate"]["status"] == "completed"
