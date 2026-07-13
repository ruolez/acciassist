"""Gap-filling: turn a completed estimate's missing facts into questionnaire
proposals through the standard advice system."""

from types import SimpleNamespace

import pytest

from app.api.admin_ai import _estimate_gaps
from tests.fixtures_estimates import (
    EXTRACTION_SPARSE,
    PipelineDispatcher,
    completed_session,
    seed_ai_settings,
    seed_jurisdictions,
)

GAP_ADVICE_REPLY = {
    "overview": "The questionnaire is missing the incident state.",
    "new_questions": [
        {
            "type": "single_choice",
            "prompt": "Which state did the accident happen in?",
            "help_text": None,
            "is_required": True,
            "config": {},
            "options": [{"label": "California", "value": "ca"}, {"label": "Texas", "value": "tx"}],
            "rationale": "State determines deadlines and fault rules.",
        }
    ],
    "question_edits": [],
}


@pytest.fixture
def dispatcher(monkeypatch) -> PipelineDispatcher:
    d = PipelineDispatcher(EXTRACTION_SPARSE)
    d.replies["questionnaire_advice"] = GAP_ADVICE_REPLY
    monkeypatch.setattr("app.services.openrouter.chat_completion", d)
    return d


class TestEstimateGaps:
    def test_merges_and_dedupes_case_insensitively(self):
        estimate = SimpleNamespace(
            missing_info=["The state where it happened.", "Medical bills."],
            internals={
                "extraction": {
                    "extraction_notes": {
                        "missing_driver_fields": ["the state where it happened.", "impact_type"]
                    }
                }
            },
        )
        assert _estimate_gaps(estimate) == [
            "The state where it happened.",
            "Medical bills.",
            "impact_type",
        ]

    def test_tolerates_missing_structures(self):
        assert _estimate_gaps(SimpleNamespace(missing_info=None, internals=None)) == []
        assert (
            _estimate_gaps(SimpleNamespace(missing_info=[" "], internals={"extraction": {}}))
            == []
        )


async def test_propose_questions_generates_focused_advice(
    admin_client, session_factory, dispatcher
):
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)

    resp = await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/propose-questions")
    assert resp.status_code == 200
    advice = resp.json()
    assert advice["proposals"][0]["kind"] == "add"
    assert advice["proposals"][0]["payload"]["prompt"].startswith("Which state")

    advice_call = next(c for c in dispatcher.calls if c["schema_name"] == "questionnaire_advice")
    prompt = advice_call["messages"][1]["content"]
    assert "missing or undocumented" in prompt
    assert "Propose ONLY questions" in prompt
    # Gaps come from both missing_info and the extraction's driver fields.
    assert "state" in prompt.lower()
    assert "- impact_type" in prompt

    # Stored on the injury type's advice row, visible to the builder too.
    itid = (await admin_client.get(f"/api/admin/intake-sessions/{sid}")).json()["injury_type_id"]
    stored = (await admin_client.get(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert stored["proposals"] == advice["proposals"]


async def test_proposals_apply_into_the_questionnaire(admin_client, session_factory, dispatcher):
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)
    advice = (
        await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/propose-questions")
    ).json()
    itid = (await admin_client.get(f"/api/admin/intake-sessions/{sid}")).json()["injury_type_id"]

    resp = await admin_client.post(
        f"/api/admin/ai/injury-types/{itid}/advice/apply",
        json={"proposal_ids": [advice["proposals"][0]["id"]]},
    )
    assert resp.status_code == 200
    questions = (await admin_client.get(f"/api/admin/injury-types/{itid}/questions")).json()
    assert any(q["prompt"].startswith("Which state") for q in questions)


async def test_location_proposal_guaranteed_when_state_is_missing(
    admin_client, session_factory, dispatcher
):
    """The sparse extraction flags the state; even though the model's advice
    reply proposes no location question, one is injected deterministically."""
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)

    advice = (
        await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/propose-questions")
    ).json()
    location = advice["proposals"][0]
    assert location["id"] == "add-location"
    assert location["payload"]["type"] == "us_state_county"

    # Applying it creates a real question of the composite type.
    itid = (await admin_client.get(f"/api/admin/intake-sessions/{sid}")).json()["injury_type_id"]
    resp = await admin_client.post(
        f"/api/admin/ai/injury-types/{itid}/advice/apply",
        json={"proposal_ids": ["add-location"]},
    )
    assert resp.status_code == 200
    questions = (await admin_client.get(f"/api/admin/injury-types/{itid}/questions")).json()
    assert any(q["type"] == "us_state_county" for q in questions)

    # Re-proposing after the question exists does not inject a duplicate.
    advice = (
        await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/propose-questions")
    ).json()
    assert not any(p["id"] == "add-location" for p in advice["proposals"])


async def test_no_missing_info_returns_400(admin_client, session_factory, monkeypatch):
    d = PipelineDispatcher()  # rich rear-end extraction → no gaps
    monkeypatch.setattr("app.services.openrouter.chat_completion", d)
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)

    resp = await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/propose-questions")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_missing_info"


async def test_incomplete_estimate_returns_409(admin_client, session_factory, dispatcher):
    from app.services.openrouter import OpenRouterError

    dispatcher.errors["case_extraction"] = OpenRouterError("timeout", "no reply")
    await seed_ai_settings(session_factory)
    sid = await completed_session(admin_client)  # estimate run fails

    resp = await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/propose-questions")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "estimate_not_ready"


async def test_unknown_session_returns_404(admin_client):
    resp = await admin_client.post(
        "/api/admin/ai/sessions/00000000-0000-0000-0000-000000000000/estimate/propose-questions"
    )
    assert resp.status_code == 404
