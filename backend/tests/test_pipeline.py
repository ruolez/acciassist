"""Orchestrator scenarios: gates, degradation, sampling majority, comps."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import CaseEstimate, EstimateStatus
from app.services.estimate_pipeline.orchestrator import STALL_AFTER
from app.services.openrouter import OpenRouterError
from tests.fixtures_estimates import (
    ADVERSARIAL_REPLY,
    EXTRACTION_NO_FAULT_SOFT,
    EXTRACTION_REAR_END_CA,
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


class TestSchemaRepair:
    """Providers can accept response_format yet let the model rename fields
    (seen with Kimi K3 on the adversarial stage) — one corrective retry."""

    DRIFTED_ADVERSARIAL = {
        "lowest_defensible_offer_pct": 40,
        "low_rationale": "Offer specials only and start a settlement now.",
        "attack_arguments": [],
    }

    async def test_adversarial_drift_is_repaired_by_retry(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.hooks["adjuster_review"] = lambda nth: (
            self.DRIFTED_ADVERSARIAL if nth == 0 else ADVERSARIAL_REPLY
        )
        public, admin = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert admin["stage_status"]["adversarial"]["status"] == "completed"
        adversarial_calls = [c for c in d.calls if c["schema_name"] == "adjuster_review"]
        assert len(adversarial_calls) == 2
        # The retry conversation carries the bad reply and the corrective ask.
        assert "schema" in adversarial_calls[1]["messages"][-1]["content"]

    async def test_adversarial_drifting_twice_degrades_without_failing_run(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.hooks["adjuster_review"] = lambda nth: self.DRIFTED_ADVERSARIAL
        public, admin = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert admin["stage_status"]["adversarial"]["status"] == "failed"

    async def test_extraction_drift_is_repaired_by_retry(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.hooks["case_extraction"] = lambda nth: (
            {"meta": "not an object"} if nth == 0 else EXTRACTION_REAR_END_CA
        )
        public, admin = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert admin["stage_status"]["extraction"]["status"] == "completed"
        assert sum(1 for c in d.calls if c["schema_name"] == "case_extraction") == 2

    async def test_enveloped_extraction_is_unwrapped_without_retry(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.hooks["case_extraction"] = lambda nth: {"case_extraction": EXTRACTION_REAR_END_CA}
        public, _ = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert public["payout_max"] > 0
        assert sum(1 for c in d.calls if c["schema_name"] == "case_extraction") == 1

    async def test_factless_extraction_is_repaired_by_retry(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.hooks["case_extraction"] = lambda nth: (
            {"meta": {}} if nth == 0 else EXTRACTION_REAR_END_CA
        )
        public, _ = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert public["payout_max"] > 0
        assert sum(1 for c in d.calls if c["schema_name"] == "case_extraction") == 2

    async def test_factless_extraction_twice_fails_instead_of_zero_estimate(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.hooks["case_extraction"] = lambda nth: {"meta": {}}
        _, admin = await _run(admin_client, session_factory, d)
        assert admin["status"] == "failed"
        assert "fact field is null" in admin["error"]

    async def test_fallback_model_rescues_unusable_extraction(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        # Calls 0-1 are the main model (initial + repair retry); call 2 is the
        # fallback model's attempt.
        d.hooks["case_extraction"] = lambda nth: (
            {"meta": {}} if nth < 2 else EXTRACTION_REAR_END_CA
        )
        public, admin = await _run(
            admin_client, session_factory, d, extraction_fallback_model="fallback/model"
        )
        assert public["status"] == "completed"
        assert public["payout_max"] > 0
        extraction_calls = [c for c in d.calls if c["schema_name"] == "case_extraction"]
        assert [c["model"] for c in extraction_calls] == [
            "test/model", "test/model", "fallback/model",
        ]
        assert admin["internals"]["extraction_model"] == "fallback/model"

    async def test_fallback_model_also_failing_fails_the_run(
        self, admin_client, session_factory, install
    ):
        d = install(PipelineDispatcher())
        d.hooks["case_extraction"] = lambda nth: {"meta": {}}
        _, admin = await _run(
            admin_client, session_factory, d, extraction_fallback_model="fallback/model"
        )
        assert admin["status"] == "failed"
        assert "fact field is null" in admin["error"]
        assert sum(1 for c in d.calls if c["schema_name"] == "case_extraction") == 4

    async def test_notes_only_extraction_counts_as_factless(
        self, admin_client, session_factory, install
    ):
        """Kimi K3 filled extraction_notes with commentary while leaving every
        fact field null; that must trigger the repair, not pass as content."""
        notes_only = {
            "extraction_notes": {
                "model_refusals": ["no fields populated — prohibited inferences"],
                "missing_driver_fields": ["incident state and county"],
            }
        }
        d = install(PipelineDispatcher())
        d.hooks["case_extraction"] = lambda nth: (
            notes_only if nth == 0 else EXTRACTION_REAR_END_CA
        )
        public, _ = await _run(admin_client, session_factory, d)
        assert public["status"] == "completed"
        assert public["payout_max"] > 0
        assert sum(1 for c in d.calls if c["schema_name"] == "case_extraction") == 2


class TestStallHealing:
    async def _pending_with_age(self, admin_client, session_factory, install, age_seconds):
        install(PipelineDispatcher())
        await seed_ai_settings(session_factory)
        await seed_jurisdictions(session_factory)
        sid = await completed_session(admin_client)
        async with session_factory() as db:
            await db.execute(
                update(CaseEstimate)
                .where(CaseEstimate.intake_session_id == uuid.UUID(str(sid)))
                .values(
                    status=EstimateStatus.pending,
                    updated_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
                )
            )
            await db.commit()
        return sid

    async def test_stale_pending_run_fails_on_admin_read(
        self, admin_client, session_factory, install
    ):
        sid = await self._pending_with_age(
            admin_client, session_factory, install, STALL_AFTER + 60
        )
        admin = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
        assert admin["status"] == "failed"
        assert "pipeline_stalled" in admin["error"]

    async def test_stale_pending_run_fails_on_public_read(
        self, admin_client, session_factory, install
    ):
        sid = await self._pending_with_age(
            admin_client, session_factory, install, STALL_AFTER + 60
        )
        public = (await admin_client.get(f"/api/intake/{sid}/estimate")).json()
        assert public["status"] == "failed"

    async def test_fresh_pending_run_is_left_alone(
        self, admin_client, session_factory, install
    ):
        sid = await self._pending_with_age(admin_client, session_factory, install, 0)
        admin = (await admin_client.get(f"/api/admin/ai/sessions/{sid}/estimate")).json()
        assert admin["status"] == "pending"
