"""End-to-end pipeline flow through the public/admin API (model calls mocked).
Deeper per-scenario coverage lives in test_pipeline.py."""

import pytest

from app.services.openrouter import OpenRouterError
from tests.fixtures_estimates import (
    PipelineDispatcher,
    completed_session,
    seed_ai_settings,
    seed_jurisdictions,
)

PUBLIC_KEYS = {
    "status", "payout_min", "payout_max", "net_min", "net_max", "fee_pct_assumed",
    "drivers", "reducers", "improvements", "warnings", "gated", "disclaimer",
}


@pytest.fixture
def dispatcher(monkeypatch) -> PipelineDispatcher:
    d = PipelineDispatcher()
    monkeypatch.setattr("app.services.openrouter.chat_completion", d)
    return d


async def test_unconfigured_completion_creates_no_estimate(admin_client):
    sid = await completed_session(admin_client)
    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body["status"] == "none"


async def test_configured_completion_runs_full_pipeline(
    admin_client, session_factory, dispatcher
):
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)

    # comps disabled by default: 1 extraction + 5 judgment samples + 1 adversarial
    by_stage = [c["schema_name"] for c in dispatcher.calls]
    assert by_stage.count("case_extraction") == 1
    assert by_stage.count("case_judgment") == 5
    assert by_stage.count("adjuster_review") == 1
    assert by_stage.count("comparable_results") == 0

    extraction_call = next(c for c in dispatcher.calls if c["schema_name"] == "case_extraction")
    assert extraction_call["temperature"] == 0.0
    assert "Were you injured?: Yes" in extraction_call["messages"][1]["content"]
    judgment_call = next(c for c in dispatcher.calls if c["schema_name"] == "case_judgment")
    assert judgment_call["temperature"] == 0.7

    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body["status"] == "completed"
    assert 0 < body["payout_min"] <= body["payout_max"]
    assert 0 <= body["net_min"] <= body["net_max"] < body["payout_max"]
    assert body["fee_pct_assumed"] == 10
    assert body["gated"] is None
    assert any("rear-end" in d.lower() for d in body["drivers"])
    assert body["reducers"] == [
        "The defense will question delayed treatment.",
        "Future care costs are not in writing.",
    ]
    assert "not legal advice" in body["disclaimer"]

    admin_body = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
    assert admin_body["status"] == "completed"
    assert admin_body["gross_min"] == body["payout_min"]
    assert admin_body["model"] == "test/model"
    stages = admin_body["stage_status"]
    assert stages["extraction"]["status"] == "completed"
    assert stages["gates"]["status"] == "completed"
    assert stages["comps"]["status"] == "skipped"
    assert stages["judgment"]["status"] == "completed"
    assert stages["adversarial"]["status"] == "completed"
    assert stages["assembly"]["status"] == "completed"
    internals = admin_body["internals"]
    assert internals["extraction"]["meta"]["state"] == "CA"
    assert len(internals["samples"]["valid"]) == 5
    assert internals["samples"]["median_tier"] == 3
    assert "assembly_trace" in internals


async def test_public_estimate_never_leaks_internals(admin_client, session_factory, dispatcher):
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)
    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert set(body) == PUBLIC_KEYS


async def test_extraction_failure_fails_run(admin_client, session_factory, dispatcher):
    await seed_ai_settings(session_factory)
    dispatcher.errors["case_extraction"] = OpenRouterError("timeout", "no response")
    sid = await completed_session(admin_client)

    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body["status"] == "failed"
    admin_body = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
    assert admin_body["error"].startswith("extraction_failed")
    assert admin_body["stage_status"]["extraction"]["status"] == "failed"


async def test_nonsense_extraction_reply_fails_run(admin_client, session_factory, monkeypatch):
    await seed_ai_settings(session_factory)

    async def _nonsense(*args, **kwargs):
        return "Sorry, I cannot help with that."

    monkeypatch.setattr("app.services.openrouter.chat_completion", _nonsense)
    sid = await completed_session(admin_client)
    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body["status"] == "failed"


async def test_recompleting_does_not_rerun_estimate(admin_client, session_factory, dispatcher):
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)
    call_count = len(dispatcher.calls)
    resp = await admin_client.post(f"/api/intake/{sid}/complete")
    assert resp.status_code == 200
    assert len(dispatcher.calls) == call_count
    body = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    assert body["status"] == "completed"


async def test_rerun_requires_configuration_and_completed_session(admin_client):
    sid = await completed_session(admin_client)
    resp = await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/rerun")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ai_not_configured"


async def test_rerun_regenerates_estimate(admin_client, session_factory, dispatcher):
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)
    first_run_calls = len(dispatcher.calls)
    resp = await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/rerun")
    assert resp.status_code == 200
    assert len(dispatcher.calls) == first_run_calls * 2
    body = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
    assert body["status"] == "completed"


async def test_case_detail_includes_estimate(admin_client, session_factory, dispatcher):
    await seed_ai_settings(session_factory)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)
    resp = await admin_client.post(
        "/api/leads",
        json={"intake_session_id": sid, "name": "Pat Smith", "email": "pat@example.com"},
    )
    assert resp.status_code == 201
    cases = (await admin_client.get("/api/admin/cases")).json()
    detail = (await admin_client.get(f"/api/admin/cases/{cases[0]['id']}")).json()
    assert detail["estimate"]["status"] == "completed"
    assert detail["estimate"]["payout_max"] == detail["estimate"]["gross_max"] > 0

    submission = (await admin_client.get(f"/api/admin/intake-sessions/{sid}")).json()
    assert submission["estimate"]["status"] == "completed"
