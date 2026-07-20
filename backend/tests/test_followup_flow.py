"""Two-phase questionnaires: initial onboarding wizard + portal follow-up."""

import pytest

from tests.conftest import claim_token_from, seed_smtp_settings
from tests.fixtures_estimates import (
    PipelineDispatcher,
    completed_session,
    seed_ai_settings,
    seed_jurisdictions,
)

FOLLOWUP_EMAIL = "followup@example.com"
FOLLOWUP_PASSWORD = "followpass123"


async def _add_followup_questions(admin_client, injury_type_id: int) -> list[int]:
    ids = []
    for body in (
        {"type": "yes_no", "phase": "follow_up", "prompt": "Are you still treating?"},
        {
            "type": "number",
            "phase": "follow_up",
            "prompt": "Roughly how much are your bills?",
            "config": {"min": 0},
        },
    ):
        resp = await admin_client.post(
            f"/api/admin/injury-types/{injury_type_id}/questions", json=body
        )
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["id"])
    return ids


async def _signed_up_case(admin_client, make_client, session_factory, sent_emails):
    """Complete an initial intake, add follow-up questions, submit a lead, and
    claim the account — returns (user_client, case_id, session_id, q_ids)."""
    await seed_smtp_settings(session_factory)
    sid = await completed_session(admin_client)
    itid = (await admin_client.get(f"/api/admin/intake-sessions/{sid}")).json()[
        "injury_type_id"
    ]
    q_ids = await _add_followup_questions(admin_client, itid)

    c = await make_client()
    resp = await c.post(
        "/api/leads",
        json={"intake_session_id": sid, "name": "Fol Low", "email": FOLLOWUP_EMAIL},
    )
    assert resp.status_code == 201
    resp = await c.post(
        "/api/auth/claim",
        json={"token": claim_token_from(sent_emails), "password": FOLLOWUP_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    cases = (await c.get("/api/me/cases")).json()
    return c, cases[0]["id"], sid, q_ids


async def test_wizard_shows_only_initial_questions(admin_client):
    itid = (
        await admin_client.post(
            "/api/admin/injury-types", json={"name": "Split", "is_published": True}
        )
    ).json()["id"]
    await admin_client.post(
        f"/api/admin/injury-types/{itid}/questions",
        json={"type": "yes_no", "prompt": "Hurt?"},
    )
    await _add_followup_questions(admin_client, itid)

    start = (
        await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
    ).json()
    prompts = [q["prompt"] for p in start["pages"] for q in p["questions"]]
    assert prompts == ["Hurt?"]


async def test_initial_answers_locked_after_completion(admin_client):
    sid = await completed_session(admin_client)
    pages = (await admin_client.get(f"/api/intake/{sid}/pages")).json()
    qid = pages["pages"][0]["questions"][0]["id"]
    resp = await admin_client.post(
        f"/api/intake/{sid}/answers",
        json={"answers": [{"question_id": qid, "value": False}]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "already_completed"


class TestPortalFollowup:
    async def test_full_flow(self, admin_client, make_client, session_factory, sent_emails):
        c, case_id, sid, (q_yes, q_num) = await _signed_up_case(
            admin_client, make_client, session_factory, sent_emails
        )

        detail = (await c.get(f"/api/me/cases/{case_id}")).json()
        assert detail["followup_pending"] is True
        assert detail["followup_total"] == 2

        followup = (await c.get(f"/api/me/cases/{case_id}/follow-up")).json()
        assert followup["completed"] is False
        assert followup["total_pages"] == 2
        assert followup["answers"] == {}

        resp = await c.post(
            f"/api/me/cases/{case_id}/follow-up/answers",
            json={"answers": [{"question_id": q_yes, "value": True}]},
        )
        assert resp.status_code == 204
        followup = (await c.get(f"/api/me/cases/{case_id}/follow-up")).json()
        assert followup["answers"] == {str(q_yes): True}

        resp = await c.post(
            f"/api/me/cases/{case_id}/follow-up/answers",
            json={"answers": [{"question_id": q_num, "value": 12000}]},
        )
        assert resp.status_code == 204

        detail = (await c.post(f"/api/me/cases/{case_id}/follow-up/complete")).json()
        assert detail["followup_pending"] is False

        followup = (await c.get(f"/api/me/cases/{case_id}/follow-up")).json()
        assert followup["completed"] is True
        resp = await c.post(
            f"/api/me/cases/{case_id}/follow-up/answers",
            json={"answers": [{"question_id": q_yes, "value": False}]},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "followup_completed"

    async def test_rejects_initial_questions_and_other_users(
        self, admin_client, make_client, session_factory, sent_emails, user_client
    ):
        c, case_id, sid, _ = await _signed_up_case(
            admin_client, make_client, session_factory, sent_emails
        )
        pages = (await admin_client.get(f"/api/intake/{sid}/pages")).json()
        initial_qid = pages["pages"][0]["questions"][0]["id"]
        resp = await c.post(
            f"/api/me/cases/{case_id}/follow-up/answers",
            json={"answers": [{"question_id": initial_qid, "value": True}]},
        )
        assert resp.status_code == 422

        # A different signed-in user cannot touch this case.
        resp = await user_client.get(f"/api/me/cases/{case_id}/follow-up")
        assert resp.status_code == 404

    async def test_complete_reruns_estimate_and_portal_shows_live_range(
        self, admin_client, make_client, session_factory, sent_emails, monkeypatch
    ):
        dispatcher = PipelineDispatcher()
        monkeypatch.setattr("app.services.openrouter.chat_completion", dispatcher)
        await seed_ai_settings(session_factory)
        await seed_jurisdictions(session_factory)

        c, case_id, sid, (q_yes, _) = await _signed_up_case(
            admin_client, make_client, session_factory, sent_emails
        )
        first_run_calls = len(dispatcher.calls)
        assert first_run_calls > 0  # the broad initial estimate already ran

        await c.post(
            f"/api/me/cases/{case_id}/follow-up/answers",
            json={"answers": [{"question_id": q_yes, "value": True}]},
        )
        detail = (await c.post(f"/api/me/cases/{case_id}/follow-up/complete")).json()
        assert len(dispatcher.calls) == first_run_calls * 2  # refined run fired

        detail = (await c.get(f"/api/me/cases/{case_id}")).json()
        assert detail["estimate_status"] == "completed"
        assert detail["estimate_refined"] is True
        # The portal range is the live pipeline estimate, not a static template.
        admin_est = (
            await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")
        ).json()
        assert detail["estimate_min"] == admin_est["gross_min"]
        assert detail["estimate_max"] == admin_est["gross_max"]

        cases = (await c.get("/api/me/cases")).json()
        assert cases[0]["followup_pending"] is False
        assert cases[0]["estimate_min"] == admin_est["gross_min"]

    async def test_complete_is_idempotent(
        self, admin_client, make_client, session_factory, sent_emails
    ):
        c, case_id, _, _ = await _signed_up_case(
            admin_client, make_client, session_factory, sent_emails
        )
        first = (await c.post(f"/api/me/cases/{case_id}/follow-up/complete")).json()
        second = (await c.post(f"/api/me/cases/{case_id}/follow-up/complete")).json()
        assert first["followup_pending"] is False
        assert second["followup_pending"] is False


@pytest.mark.parametrize("phase", ["initial", "follow_up"])
async def test_question_phase_roundtrip(admin_client, phase):
    itid = (
        await admin_client.post(
            "/api/admin/injury-types", json={"name": f"Phase {phase}", "is_published": False}
        )
    ).json()["id"]
    q = (
        await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "yes_no", "phase": phase, "prompt": "P?"},
        )
    ).json()
    assert q["phase"] == phase
    flipped = "follow_up" if phase == "initial" else "initial"
    updated = (
        await admin_client.put(
            f"/api/admin/injury-types/{itid}/questions/{q['id']}",
            json={"type": "yes_no", "phase": flipped, "prompt": "P?"},
        )
    ).json()
    assert updated["phase"] == flipped
