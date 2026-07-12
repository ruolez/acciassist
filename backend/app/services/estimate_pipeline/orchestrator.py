"""Pipeline orchestrator — the background task behind every estimate.

Sequencing: extraction → jurisdiction gates (code) → [comps ∥ judgment
samples ∥ adversarial] → assembly (code). Extraction or judgment failure
fails the run; comps and adversarial degrade gracefully. Like the old
single-shot task, run_pipeline opens its own DB session and never raises —
failures land in case_estimates.error, and per-stage progress is committed
as it happens so the admin view can watch a run advance.
"""

import asyncio
import logging
import time
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    CaseEstimate,
    EstimateStatus,
    InjuryType,
    IntakeAnswer,
    IntakeSession,
    JurisdictionRule,
    Question,
)
from app.services import email as email_service
from app.services.email import get_app_settings
from app.services.estimate_pipeline import adversarial as adversarial_stage
from app.services.estimate_pipeline import comps as comps_stage
from app.services.estimate_pipeline import judgment as judgment_stage
from app.services.estimate_pipeline.assembly import (
    AdversarialSummary,
    CompsSummary,
    assemble,
    assemble_gated,
)
from app.services.estimate_pipeline.extraction import run_extraction
from app.services.estimate_pipeline.gates import evaluate_gates
from app.services.openrouter import ai_configured
from app.services.summary import answer_display_value

logger = logging.getLogger(__name__)

PIPELINE_TIMEOUT = 240.0
ADVERSARIAL_TIMEOUT = 60.0


async def build_qa_triples(
    db: AsyncSession, session: IntakeSession
) -> list[tuple[str, str, str]]:
    """(slug, prompt, display answer) for every question, in wizard order.
    Slugs are the extraction's source_field vocabulary."""
    questions = await db.scalars(
        select(Question)
        .where(Question.injury_type_id == session.injury_type_id)
        .order_by(Question.display_order)
        .options(selectinload(Question.options))
    )
    answers = {
        a.question_id: a.value
        for a in await db.scalars(
            select(IntakeAnswer).where(IntakeAnswer.session_id == session.id)
        )
    }
    triples = []
    for q in questions:
        labels = {o.value: o.label for o in q.options}
        if q.id in answers:
            display = answer_display_value(q.type, answers[q.id], labels)
        else:
            display = "(not answered)"
        triples.append((q.slug, q.prompt, display or "(not answered)"))
    return triples


def _merge(current: dict | None, patch: dict) -> dict:
    # Reassignment (not mutation) so SQLAlchemy detects the JSONB change.
    return {**(current or {}), **patch}


async def _set_stage(
    db: AsyncSession,
    estimate: CaseEstimate,
    name: str,
    status: str,
    ms: int | None = None,
    error: str | None = None,
) -> None:
    entry: dict = {"status": status}
    if ms is not None:
        entry["ms"] = ms
    if error is not None:
        entry["error"] = error[:2000]
    estimate.stage_status = _merge(estimate.stage_status, {name: entry})
    await db.commit()


async def _fail(db: AsyncSession, estimate: CaseEstimate, error: str) -> None:
    estimate.status = EstimateStatus.failed
    estimate.error = error[:2000]
    await db.commit()


class _Timer:
    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.ms = int((time.monotonic() - self._start) * 1000)


async def _guarded(coro, timeout: float):
    """Run a degradable stage: returns (value, None) or (None, error_str)."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout), None
    except Exception as exc:  # noqa: BLE001 — degradable by design
        return None, f"{type(exc).__name__}: {exc}"


async def run_pipeline(session_id: uuid.UUID) -> None:
    """Background task entry point. Never raises."""
    factory = email_service.get_session_factory()
    async with factory() as db:
        estimate = await db.scalar(
            select(CaseEstimate).where(CaseEstimate.intake_session_id == session_id)
        )
        if estimate is None:
            logger.warning("run_pipeline: no estimate row for session %s", session_id)
            return
        try:
            async with asyncio.timeout(PIPELINE_TIMEOUT):
                await _run(db, estimate, session_id)
        except TimeoutError:
            await _fail(db, estimate, "pipeline_timeout: the estimate did not finish in time")
        except Exception as exc:  # noqa: BLE001 — background task must not raise
            logger.exception("estimate pipeline for session %s crashed", session_id)
            await _fail(db, estimate, f"pipeline_error: {exc}")


async def _run(db: AsyncSession, estimate: CaseEstimate, session_id: uuid.UUID) -> None:
    session = await db.get(IntakeSession, session_id)
    settings = await get_app_settings(db)
    if session is None or not ai_configured(settings):
        await _fail(db, estimate, "ai_not_configured: AI is not configured")
        return
    injury_type_name = (
        await db.scalar(select(InjuryType.name).where(InjuryType.id == session.injury_type_id))
        or "Unknown"
    )
    api_key, model = settings.openrouter_api_key, settings.openrouter_model
    referer = settings.app_base_url
    estimate.model = model

    # ── Stage 1: extraction (failure fails the run) ────────────────────
    triples = await build_qa_triples(db, session)
    try:
        with _Timer() as t:
            extraction = await run_extraction(api_key, model, injury_type_name, triples, referer)
    except Exception as exc:  # noqa: BLE001 — any extraction problem fails the run
        await _set_stage(db, estimate, "extraction", "failed", error=str(exc))
        await _fail(db, estimate, f"extraction_failed: {exc}")
        return
    estimate.internals = _merge(
        estimate.internals, {"extraction": extraction.model_dump(mode="json")}
    )
    await _set_stage(db, estimate, "extraction", "completed", ms=t.ms)

    # ── Stage 2: jurisdiction + gates (pure code) ──────────────────────
    rule = None
    if extraction.meta.state:
        rule = await db.get(JurisdictionRule, extraction.meta.state)
    gate = evaluate_gates(extraction, rule, date.today())
    estimate.internals = _merge(
        estimate.internals,
        {
            "jurisdiction": {
                "state": extraction.meta.state,
                "rule_found": rule is not None,
                "comparative_rule": rule.comparative_rule if rule else None,
                "no_fault": rule.no_fault if rule else None,
                "sol_years_pi": rule.sol_years_pi if rule else None,
                "needs_review": rule.needs_review if rule else None,
                "gate": {"blocked": gate.blocked, "code": gate.code},
            }
        },
    )
    await _set_stage(db, estimate, "gates", "completed")

    if gate.blocked:
        result = assemble_gated(extraction, rule, gate)
        for name in ("comps", "judgment", "adversarial"):
            estimate.stage_status = _merge(estimate.stage_status, {name: {"status": "skipped"}})
        _persist_result(estimate, result)
        await _set_stage(db, estimate, "assembly", "completed")
        return

    # ── Stages 3/4/5 concurrently ──────────────────────────────────────
    comps_enabled = bool(settings.comps_enabled)
    comps_model = comps_stage.resolve_comps_model(settings.comps_model, model)

    async def _no_comps():
        return None, "disabled"

    comps_coro = (
        _guarded(
            comps_stage.run_comps(api_key, comps_model, extraction, injury_type_name, referer),
            timeout=comps_stage.COMPS_TIMEOUT,
        )
        if comps_enabled
        else _no_comps()
    )
    sample_count = max(1, min(int(settings.sample_count or 5), 9))
    samples_coro = asyncio.gather(
        *(
            judgment_stage.sample_once(api_key, model, extraction, referer)
            for _ in range(sample_count)
        ),
        return_exceptions=True,
    )
    adversarial_coro = _guarded(
        adversarial_stage.run_adversarial(api_key, model, extraction, rule, referer),
        timeout=ADVERSARIAL_TIMEOUT,
    )
    (comps_result, comps_error), sample_results, (adv_result, adv_error) = await asyncio.gather(
        comps_coro, samples_coro, adversarial_coro
    )

    # Comps: optional, degradable.
    comps: CompsSummary | None = comps_result
    if not comps_enabled:
        await _set_stage(db, estimate, "comps", "skipped")
    elif comps is None:
        await _set_stage(db, estimate, "comps", "failed", error=comps_error)
    else:
        estimate.internals = _merge(
            estimate.internals, {"comps": {"model": comps_model, "comps": comps.comps}}
        )
        await _set_stage(db, estimate, "comps", "completed")

    # Judgment: needs a majority of valid samples.
    valid_samples = [r for r in sample_results if isinstance(r, judgment_stage.JudgmentSample)]
    sample_errors = [
        str(r) for r in sample_results if not isinstance(r, judgment_stage.JudgmentSample)
    ]
    estimate.internals = _merge(
        estimate.internals,
        {
            "samples": {
                "requested": sample_count,
                "valid": [s.model_dump(mode="json") for s in valid_samples],
                "errors": sample_errors[:5],
            }
        },
    )
    if len(valid_samples) < judgment_stage.minimum_valid_samples(sample_count):
        await _set_stage(
            db, estimate, "judgment", "failed",
            error=f"only {len(valid_samples)}/{sample_count} samples valid",
        )
        await _fail(
            db,
            estimate,
            f"judgment_failed: only {len(valid_samples)} of {sample_count} judgment "
            f"samples were usable ({'; '.join(sample_errors[:2])})",
        )
        return
    judgment = judgment_stage.aggregate_samples(valid_samples)
    estimate.internals = _merge(
        estimate.internals,
        {
            "samples": {
                **estimate.internals["samples"],
                "median_tier": judgment.median_tier,
                "median_liability_pct": judgment.median_liability_pct,
                "tier_spread": judgment.tier_spread,
                "liability_spread": judgment.liability_spread,
            }
        },
    )
    await _set_stage(db, estimate, "judgment", "completed")

    # Adversarial: degradable.
    adversarial: AdversarialSummary | None = adv_result
    if adversarial is None:
        await _set_stage(db, estimate, "adversarial", "failed", error=adv_error)
    else:
        estimate.internals = _merge(
            estimate.internals,
            {
                "adversarial": {
                    "lowest_defensible_pct_of_specials": (
                        adversarial.lowest_defensible_pct_of_specials
                    ),
                    "low_rationale": adversarial.low_rationale,
                    "attack_arguments": adversarial.attack_arguments,
                }
            },
        )
        await _set_stage(db, estimate, "adversarial", "completed")

    # ── Stage 6: assembly (pure code) ──────────────────────────────────
    result = assemble(
        extraction,
        rule,
        gate,
        judgment,
        adversarial,
        comps,
        fee_pct=float(settings.contingency_fee_pct or 33.3),
    )
    estimate.internals = _merge(estimate.internals, {"assembly_trace": result["trace"]})
    _persist_result(estimate, result)
    await _set_stage(db, estimate, "assembly", "completed")


def _persist_result(estimate: CaseEstimate, result: dict) -> None:
    """Map the assembled result onto the row, mirroring gross into the legacy
    payout columns. The caller commits (via the following _set_stage)."""
    estimate.gross_min = result["gross_min"]
    estimate.gross_max = result["gross_max"]
    estimate.net_min = result["net_min"]
    estimate.net_max = result["net_max"]
    estimate.payout_min = result["gross_min"]
    estimate.payout_max = result["gross_max"]
    estimate.case_cost_min = result["case_cost_min"]
    estimate.case_cost_max = result["case_cost_max"]
    estimate.confidence = result["confidence"]
    estimate.reasoning = result["summary"]
    estimate.missing_info = result["improvements"]
    estimate.result = {k: v for k, v in result.items() if k != "trace"}
    estimate.error = None
    estimate.status = EstimateStatus.completed
