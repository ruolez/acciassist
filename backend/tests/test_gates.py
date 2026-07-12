from dataclasses import dataclass
from datetime import date, timedelta

from app.services.estimate_pipeline.canonical import CanonicalExtraction
from app.services.estimate_pipeline.gates import (
    SOL_WARNING_WINDOW_DAYS,
    evaluate_gates,
    sol_expiry,
)

TODAY = date(2026, 7, 12)


@dataclass
class Rule:
    state_code: str = "CA"
    state_name: str = "California"
    comparative_rule: str = "pure"
    no_fault: bool = False
    pip_threshold_note: str | None = None
    sol_years_pi: float = 2.0
    sol_note: str | None = None
    noneconomic_cap: int | None = None
    needs_review: bool = True


def extraction(**overrides) -> CanonicalExtraction:
    return CanonicalExtraction.model_validate(overrides)


def codes(result) -> list[str]:
    return [w.code for w in result.warnings]


class TestBlockingGates:
    def test_release_signed_blocks(self):
        r = evaluate_gates(extraction(gates={"release_signed": True}), Rule(), TODAY)
        assert (r.blocked, r.code) == (True, "release_signed")

    def test_fatality_routes_to_wrongful_death(self):
        r = evaluate_gates(extraction(gates={"fatality_involved": True}), Rule(), TODAY)
        assert (r.blocked, r.code) == (True, "wrongful_death")

    def test_workplace_injury_blocks(self):
        r = evaluate_gates(extraction(gates={"workplace_injury": True}), Rule(), TODAY)
        assert (r.blocked, r.code) == (True, "workers_comp")

    def test_trespasser_blocks(self):
        r = evaluate_gates(
            extraction(gates={"claimant_status_premises": "trespasser"}), Rule(), TODAY
        )
        assert (r.blocked, r.code) == (True, "trespasser_status")

    def test_sol_expired_day_after_blocks_day_before_does_not(self):
        rule = Rule(sol_years_pi=2.0)
        expiry = sol_expiry(TODAY - timedelta(days=800), 2.0)
        assert expiry < TODAY  # sanity: 800 days > 2 years

        expired = evaluate_gates(
            extraction(meta={"incident_date": (TODAY - timedelta(days=800)).isoformat()}),
            rule,
            TODAY,
        )
        assert (expired.blocked, expired.code) == (True, "sol_expired")
        assert expiry.isoformat() in expired.explanation

        # An incident whose deadline is tomorrow is not blocked.
        recent_incident = TODAY + timedelta(days=1) - timedelta(days=round(2 * 365.25))
        alive = evaluate_gates(
            extraction(meta={"incident_date": recent_incident.isoformat()}), rule, TODAY
        )
        assert alive.blocked is False
        assert "sol_approaching" in codes(alive)

    def test_sol_warning_only_inside_window(self):
        rule = Rule(sol_years_pi=2.0)
        inside = TODAY + timedelta(days=SOL_WARNING_WINDOW_DAYS - 1) - timedelta(
            days=round(2 * 365.25)
        )
        outside = TODAY + timedelta(days=SOL_WARNING_WINDOW_DAYS + 30) - timedelta(
            days=round(2 * 365.25)
        )
        near = evaluate_gates(extraction(meta={"incident_date": inside.isoformat()}), rule, TODAY)
        far = evaluate_gates(extraction(meta={"incident_date": outside.isoformat()}), rule, TODAY)
        assert "sol_approaching" in codes(near)
        deadline = next(w for w in near.warnings if w.code == "sol_approaching").deadline
        assert deadline == sol_expiry(inside, 2.0)
        assert "sol_approaching" not in codes(far)

    def test_no_rule_or_no_date_skips_sol(self):
        old = extraction(meta={"incident_date": "2010-01-01"})
        assert evaluate_gates(old, None, TODAY).blocked is False
        assert evaluate_gates(extraction(), Rule(), TODAY).blocked is False


class TestNoFaultThreshold:
    def _mva(self, **injury) -> CanonicalExtraction:
        return extraction(meta={"case_type": "motor_vehicle", "state": "NY"}, injury=injury)

    def test_soft_tissue_in_no_fault_state_is_gated(self):
        rule = Rule(state_code="NY", state_name="New York", no_fault=True,
                    pip_threshold_note="Serious-injury threshold.")
        r = evaluate_gates(self._mva(), rule, TODAY)
        assert (r.blocked, r.code) == (True, "no_fault_threshold")
        assert "Serious-injury threshold." in r.explanation

    def test_objective_finding_clears_threshold(self):
        rule = Rule(no_fault=True)
        r = evaluate_gates(
            self._mva(objective_finding={"status": "imaging_positive"}), rule, TODAY
        )
        assert r.blocked is False

    def test_injections_clear_threshold(self):
        r = evaluate_gates(
            self._mva(treatment_ladder={"highest_reached": "injections"}),
            Rule(no_fault=True),
            TODAY,
        )
        assert r.blocked is False

    def test_premises_case_not_gated_by_no_fault(self):
        r = evaluate_gates(
            extraction(meta={"case_type": "slip_trip_fall"}), Rule(no_fault=True), TODAY
        )
        assert r.blocked is False


class TestWarnings:
    def test_state_unknown_warns(self):
        assert "state_unknown" in codes(evaluate_gates(extraction(), None, TODAY))

    def test_government_defendant_warns_time_critical(self):
        r = evaluate_gates(extraction(gates={"government_defendant": True}), Rule(), TODAY)
        w = next(w for w in r.warnings if w.code == "notice_of_claim")
        assert w.severity == "time_critical"

    def test_unpreserved_surveillance_warns(self):
        r = evaluate_gates(
            extraction(liability={"evidence": {"surveillance_exists": True}}), Rule(), TODAY
        )
        assert "preserve_surveillance" in codes(r)

    def test_preserved_surveillance_does_not_warn(self):
        r = evaluate_gates(
            extraction(
                liability={
                    "evidence": {
                        "surveillance_exists": True,
                        "surveillance_preservation_sent": True,
                    }
                }
            ),
            Rule(),
            TODAY,
        )
        assert "preserve_surveillance" not in codes(r)

    def test_treatment_gap_warns(self):
        r = evaluate_gates(
            extraction(injury={"treatment_gap": {"duration_bucket": "60_plus_days"}}),
            Rule(),
            TODAY,
        )
        assert "treatment_gap" in codes(r)

    def test_warnings_survive_on_blocked_result(self):
        r = evaluate_gates(
            extraction(
                gates={"release_signed": True, "government_defendant": True},
            ),
            Rule(),
            TODAY,
        )
        assert r.blocked is True
        assert "notice_of_claim" in codes(r)
