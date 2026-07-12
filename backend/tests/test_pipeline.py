"""Orchestrator scenarios: gates, degradation, sampling majority, comps."""

import pytest

from app.services.openrouter import OpenRouterError
from tests.fixtures_estimates import (
    EXTRACTION_NO_FAULT_SOFT,
    EXTRACTION_SOL_EXPIRED,
    EXTRACTION_SPARSE,
    EXTRACTION_TRESPASSER,
    JUDGMENT_REPLY,
    PipelineDispatcher,
    completed_session,
    seed_ai_settings,
    seed_jurisdictions,
)


@pytest.fixture
def install(monkeypatch):
    def _install(dispatcher: PipelineDispatcher) -> PipelineDispatcher:
        monkeypatch.setattr("app.services.openrouter.chat_completion", dispatcher)
        return dispatcher

    return _install


async def _run(admin_client, session_factory, dispatcher, **settings):
    await seed_ai_settings(session_factory, **settings)
    await seed_jurisdictions(session_factory)
    sid = await completed_session(admin_client)
    public = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
    admin = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
    return public, admin


class TestGatedScenarios:
    async def test_sol_expired_returns_gated_zero(self, admin_client, session_factory, install):
        d = install(PipelineDispatcher(EXTRACTION_SOL_EXPIRED))
        public, admin = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert public["gated"]["code"] == "sol_expired"
        assert "Tennessee" in public["gated"]["explanation"]
        assert public["payout_min"] == public["payout_max"] == 0
        # Gates short-circuit the model stages entirely.
        assert [c["schema_name"] for c in d.calls] == ["case_extraction"]
        assert admin["stage_status"]["judgment"]["status"] == "skipped"
        assert admin["stage_status"]["comps"]["status"] == "skipped"

    async def test_trespasser_premises_is_gated(self, admin_client, session_factory, install):
        d = install(PipelineDispatcher(EXTRACTION_TRESPASSER))
        public, _ = await _run(admin_client, session_factory, d)
        assert public["gated"]["code"] == "trespasser_status"

    async def test_no_fault_below_threshold_is_gated(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher(EXTRACTION_NO_FAULT_SOFT))
        public, _ = await _run(admin_client, session_factory, d)
        assert public["gated"]["code"] == "no_fault_threshold"
        assert "New York" in public["gated"]["title"]


class TestSparseCase:
    async def test_unknown_state_widens_and_warns(self, admin_client, session_factory, install):
        d = install(PipelineDispatcher(EXTRACTION_SPARSE))
        public, admin = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert any(w["code"] == "state_unknown" for w in public["warnings"])
        assert admin["confidence"] == "low"
        assert any("state" in i.lower() for i in public["improvements"])


class TestDegradation:
    async def test_comps_failure_does_not_fail_run(self, admin_client, session_factory, install):
        d = install(PipelineDispatcher())
        d.errors["comparable_results"] = OpenRouterError("timeout", "web search timed out")
        public, admin = await _run(
            admin_client, session_factory, d, comps_enabled=True
        )
        assert public["status"] == "completed"
        assert admin["stage_status"]["comps"]["status"] == "failed"
        assert "timed out" in admin["stage_status"]["comps"]["error"]

    async def test_comps_success_uses_online_model_and_stores_results(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        public, admin = await _run(admin_client, session_factory, d, comps_enabled=True)
        comps_call = next(c for c in d.calls if c["schema_name"] == "comparable_results")
        assert comps_call["model"] == "test/model:online"
        assert comps_call["require_parameters"] is False
        assert admin["stage_status"]["comps"]["status"] == "completed"
        stored = admin["internals"]["comps"]["comps"]
        assert len(stored) == 2
        # The entry without a source_url got the citation annotation merged in.
        assert stored[1]["source_url"] == "https://example.com/cited"
        assert public["status"] == "completed"

    async def test_dedicated_comps_model_used_verbatim(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        await _run(
            admin_client, session_factory, d,
            comps_enabled=True, comps_model="perplexity/sonar",
        )
        comps_call = next(c for c in d.calls if c["schema_name"] == "comparable_results")
        assert comps_call["model"] == "perplexity/sonar"

    async def test_adversarial_failure_degrades_to_fallback_reducers(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher(EXTRACTION_SPARSE))
        d.errors["adjuster_review"] = OpenRouterError("timeout", "no reply")
        public, admin = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert admin["stage_status"]["adversarial"]["status"] == "failed"
        # Fallback reducers come from extraction facts (no imaging finding).
        assert any("imaging" in r.lower() for r in public["reducers"])


class TestSamplingMajority:
    async def test_minority_of_valid_samples_fails_run(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.judgment_hook = lambda nth: (
            JUDGMENT_REPLY if nth < 2 else OpenRouterError("rate_limited", "slow down")
        )
        public, admin = await _run(admin_client, session_factory, d)
        assert public["status"] == "failed"
        assert admin["error"].startswith("judgment_failed")
        assert admin["stage_status"]["judgment"]["status"] == "failed"

    async def test_majority_of_valid_samples_suffices(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.judgment_hook = lambda nth: (
            JUDGMENT_REPLY if nth < 3 else OpenRouterError("rate_limited", "slow down")
        )
        public, admin = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert len(admin["internals"]["samples"]["valid"]) == 3

    async def test_sample_count_setting_controls_call_volume(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        await _run(admin_client, session_factory, d, sample_count=3)
        assert sum(1 for c in d.calls if c["schema_name"] == "case_judgment") == 3

    async def test_spread_across_samples_widens_range(
        self, admin_client, session_factory, install
    ):
        tight = install(PipelineDispatcher())
        _, admin_tight = await _run(admin_client, session_factory, tight)

        # Re-run the same session with disagreeing samples via rerun endpoint.
        varied_replies = [
            dict(JUDGMENT_REPLY, severity_tier=2, defendant_liability_pct=60),
            dict(JUDGMENT_REPLY, severity_tier=3, defendant_liability_pct=90),
            dict(JUDGMENT_REPLY, severity_tier=4, defendant_liability_pct=95),
            dict(JUDGMENT_REPLY, severity_tier=3, defendant_liability_pct=85),
            dict(JUDGMENT_REPLY, severity_tier=2, defendant_liability_pct=70),
        ]
        tight.judgment_hook = lambda nth: varied_replies[nth % 5]
        sessions = (await admin_client.get("/api/admin/intake-sessions")).json()
        sid = sessions[0]["id"]
        resp = await admin_client.post(f"/api/admin/ai/sessions/{sid}/estimate/rerun")
        assert resp.status_code == 200
        admin_varied = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()

        tight_width = admin_tight["result"]["width"]
        varied_width = admin_varied["result"]["width"]
        assert varied_width > tight_width
