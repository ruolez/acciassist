from dataclasses import dataclass

import pytest

from app.services.estimate_pipeline import assembly
from app.services.estimate_pipeline.assembly import (
    CASE_COSTS_BY_TIER,
    CONTRIBUTORY_SURVIVAL_FACTOR,
    LIEN_CAP_PCT_OF_GROSS,
    LIEN_PCT_BY_PAYOR,
    TIER_MULTIPLIERS,
    UNDOCUMENTED_MEDICAL_WEIGHT,
    WIDTH_MAX,
    WIDTH_MIN,
    AdversarialSummary,
    CompsSummary,
    JudgmentAggregate,
    apply_adversarial_floor,
    apply_comps_anchor,
    apply_liability,
    assemble,
    assemble_gated,
    compute_net,
    count_missing_drivers,
    derive_confidence,
    general_damages,
    range_width,
    round_estimate,
    weight_specials,
)
from app.services.estimate_pipeline.canonical import CanonicalExtraction
from app.services.estimate_pipeline.gates import GateResult, evaluate_gates


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


def money(amount: float | None, documented: bool = False) -> dict:
    return {"amount": amount, "documented": documented}


class TestWeightSpecials:
    def test_documented_medical_counts_fully_undocumented_halved(self):
        documented = weight_specials(
            extraction(economic={"medical_billed_to_date": money(10_000, True)})
        )
        undocumented = weight_specials(
            extraction(economic={"medical_billed_to_date": money(10_000, False)})
        )
        assert documented.weighted_medical == 10_000
        assert undocumented.weighted_medical == 10_000 * UNDOCUMENTED_MEDICAL_WEIGHT
        assert documented.documented_medical == 10_000
        assert undocumented.documented_medical == 0

    def test_future_care_in_writing_vs_claimed(self):
        base = {"economic": {"future_medical": money(20_000)}}
        claimed = weight_specials(extraction(**base))
        in_writing = weight_specials(
            extraction(
                economic={"future_medical": money(20_000)},
                injury={"treatment_ladder": {"future_care_in_writing": True}},
            )
        )
        assert claimed.weighted_future_care == 20_000 * 0.3
        assert in_writing.weighted_future_care == 20_000

    @pytest.mark.parametrize(
        ("employment", "verifiable", "expected_weight"),
        [
            ("w2", True, 1.0),
            ("w2", False, 0.5),
            ("self_employed_1099", True, 0.75),
            ("self_employed_1099", False, 0.35),
            ("unknown", True, 0.5),
            (None, False, 0.25),
        ],
    )
    def test_wage_weights(self, employment, verifiable, expected_weight):
        s = weight_specials(
            extraction(
                economic={
                    "lost_wages": {
                        "claimed": money(8_000),
                        "employment_type": employment,
                        "verifiable": verifiable,
                    }
                }
            )
        )
        assert s.weighted_wages == 8_000 * expected_weight

    def test_cash_wages_excluded_and_flagged(self):
        s = weight_specials(
            extraction(
                economic={
                    "lost_wages": {
                        "claimed": money(8_000),
                        "employment_type": "cash_unreported",
                        "verifiable": True,
                    }
                }
            )
        )
        assert s.weighted_wages == 0.0
        assert len(s.flags) == 1


class TestGeneralDamages:
    @pytest.mark.parametrize("tier", [1, 2, 3, 4, 5])
    def test_tier_multipliers_applied(self, tier):
        lo_mult, hi_mult = TIER_MULTIPLIERS[tier]
        assert general_damages(10_000, tier, None) == (10_000 * lo_mult, 10_000 * hi_mult)

    def test_noneconomic_cap_limits_both_bounds(self):
        assert general_damages(100_000, 5, 300_000) == (300_000, 300_000)

    def test_out_of_range_tier_clamped(self):
        assert general_damages(10_000, 9, None) == general_damages(10_000, 5, None)


class TestApplyLiability:
    def test_pure_scales_by_defendant_share(self):
        low, high, warnings = apply_liability(10_000, 20_000, 60, "pure")
        assert (low, high) == (6_000, 12_000)
        assert warnings == []

    @pytest.mark.parametrize(
        ("rule", "defendant_pct", "barred"),
        [
            ("modified_50", 51, False),  # fault 49 → recovers
            ("modified_50", 50, True),  # fault 50 → barred
            ("modified_51", 50, False),  # fault 50 → recovers at exactly 50
            ("modified_51", 49, True),  # fault 51 → barred
        ],
    )
    def test_modified_bars_at_threshold(self, rule, defendant_pct, barred):
        low, high, warnings = apply_liability(10_000, 20_000, defendant_pct, rule)
        if barred:
            assert (low, high) == (0.0, 0.0)
            assert [w.code for w in warnings] == ["comparative_bar"]
        else:
            assert low == pytest.approx(10_000 * defendant_pct / 100)

    def test_contributory_any_fault_craters_range(self):
        low, high, warnings = apply_liability(10_000, 20_000, 90, "contributory")
        assert low == 0.0
        assert high == 20_000 * CONTRIBUTORY_SURVIVAL_FACTOR
        assert [w.code for w in warnings] == ["contributory_bar"]

    def test_contributory_with_clean_facts_unchanged(self):
        low, high, warnings = apply_liability(10_000, 20_000, 100, "contributory")
        assert (low, high) == (10_000, 20_000)
        assert warnings == []

    def test_unknown_rule_scales_like_pure(self):
        low, high, _ = apply_liability(10_000, 20_000, 80, None)
        assert (low, high) == (8_000, 16_000)


class TestCompsAnchor:
    def test_pulls_center_toward_comps_geometrically(self):
        low, high = apply_comps_anchor(10_000, 20_000, 30_000)
        center = 15_000
        expected_scale = (center**0.7 * 30_000**0.3) / center
        assert low == pytest.approx(10_000 * expected_scale)
        assert high == pytest.approx(20_000 * expected_scale)
        assert high / low == pytest.approx(2.0)  # ratio preserved

    @pytest.mark.parametrize("median", [None, 2_000, 100_000])
    def test_ignored_when_absent_or_implausible(self, median):
        assert apply_comps_anchor(10_000, 20_000, median) == (10_000, 20_000)

    def test_weighted_median_prefers_published_verdicts(self):
        comps = CompsSummary(
            comps=[
                {"amount": 10_000, "source_quality": "firm_marketing"},
                {"amount": 50_000, "source_quality": "published_verdict"},
                {"amount": 90_000, "source_quality": "firm_marketing"},
            ]
        )
        assert comps.weighted_median() == 50_000

    def test_weighted_median_drops_junk_amounts(self):
        comps = CompsSummary(comps=[{"amount": 0}, {"amount": 999_000_000}])
        assert comps.weighted_median() is None


class TestRangeWidth:
    def test_monotone_in_every_input(self):
        base = range_width(0, 0, 0)
        assert base == WIDTH_MIN
        assert range_width(1, 0, 0) > base
        assert range_width(0, 40, 0) > base
        assert range_width(0, 0, 2) > base

    def test_clamped_to_max(self):
        assert range_width(4, 100, 20) == WIDTH_MAX

    def test_missing_driver_contribution_caps(self):
        assert range_width(0, 0, 8) == range_width(0, 0, 100)


class TestMissingDrivers:
    def test_counts_nulls_and_undocumented_dollars(self):
        sparse = extraction(
            economic={"medical_billed_to_date": money(5_000, False)},
            extraction_notes={"missing_driver_fields": ["state", "impact_type"]},
        )
        # 2 named + 1 undocumented money + 2 for unknown state + 1 unknown imaging
        assert count_missing_drivers(sparse) == 6

    def test_complete_case_counts_zero(self):
        complete = extraction(
            meta={"state": "CA"},
            injury={"objective_finding": {"status": "imaging_positive"}},
            economic={"medical_billed_to_date": money(5_000, True)},
        )
        assert count_missing_drivers(complete) == 0


class TestAdversarialFloorAndCaps:
    def test_floor_blends_down_only(self):
        # adversarial says 80% of 10k specials = 8k; our low is 12k → blend to 10k
        assert apply_adversarial_floor(12_000, 80, 10_000) == 10_000
        # adversarial number above our low → untouched
        assert apply_adversarial_floor(5_000, 80, 10_000) == 5_000
        assert apply_adversarial_floor(12_000, None, 10_000) == 12_000

    def test_round_estimate_steps(self):
        assert round_estimate(4_130) == 4_250 or round_estimate(4_130) == 4_000
        assert round_estimate(4_130) % 250 == 0
        assert round_estimate(23_456) % 500 == 0
        assert round_estimate(123_456) % 1000 == 0
        assert round_estimate(-50) == 0

    @pytest.mark.parametrize(
        ("width", "missing", "expected"),
        [(0.10, 1, "high"), (0.10, 3, "medium"), (0.25, 4, "medium"), (0.25, 5, "low"),
         (0.45, 0, "low")],
    )
    def test_confidence_bands(self, width, missing, expected):
        assert derive_confidence(width, missing) == expected


class TestComputeNet:
    def test_fee_costs_and_lien_deducted(self):
        net = compute_net(100_000, 33.3, 5_000, "medicare", 20_000)
        lien = LIEN_PCT_BY_PAYOR["medicare"] * 20_000
        assert net == pytest.approx(100_000 * (1 - 0.333) - 5_000 - lien)

    def test_lien_capped_at_share_of_gross(self):
        net = compute_net(10_000, 33.3, 0, "letter_of_protection", 100_000)
        assert net == pytest.approx(10_000 * (1 - 0.333) - LIEN_CAP_PCT_OF_GROSS * 10_000)

    def test_net_floored_at_zero(self):
        assert compute_net(3_000, 40, 5_000, "medicare", 10_000) == 0.0


REAR_END_DOCUMENTED = dict(
    meta={"case_type": "motor_vehicle", "state": "CA", "incident_date": "2026-01-15"},
    injury={
        "objective_finding": {"status": "imaging_positive", "finding_verbatim": "herniation"},
        "treatment_ladder": {"highest_reached": "injections"},
    },
    economic={
        "medical_billed_to_date": money(18_400, True),
        "liens": {"payor_type": "private"},
    },
    liability={
        "evidence": {"citation_issued_to": "other_party", "police_report": True},
        "mva": {"impact_type": "rear_ended", "property_damage_level": "severe"},
    },
)


class TestAssemble:
    def _assemble(self, x: CanonicalExtraction, rule="default", **kwargs):
        if rule == "default":
            rule = Rule()
        judgment = kwargs.pop(
            "judgment",
            JudgmentAggregate(
                median_tier=3, median_liability_pct=95, tier_spread=0, liability_spread=5
            ),
        )
        gate = kwargs.pop("gate", GateResult())
        return assemble(
            x,
            rule,
            gate,
            judgment,
            kwargs.pop("adversarial", None),
            kwargs.pop("comps", None),
            fee_pct=kwargs.pop("fee_pct", 33.3),
        )

    def test_documented_rear_end_produces_coherent_result(self):
        result = self._assemble(extraction(**REAR_END_DOCUMENTED))
        assert result["gated"] is None
        assert 0 < result["gross_min"] < result["gross_max"]
        assert 0 <= result["net_min"] <= result["net_max"] < result["gross_max"]
        assert result["confidence"] in ("medium", "high")
        assert (result["case_cost_min"], result["case_cost_max"]) == CASE_COSTS_BY_TIER[3]
        assert any("rear-end" in d.lower() for d in result["drivers"])
        assert result["fee_pct"] == 33.3
        assert result["trace"]["specials"]["total"] == 18_400

    def test_sparse_case_is_wider_and_lower_confidence(self):
        rich = self._assemble(extraction(**REAR_END_DOCUMENTED))
        sparse = self._assemble(
            extraction(
                meta={"case_type": "motor_vehicle"},
                economic={"medical_billed_to_date": money(18_400, False)},
                extraction_notes={"missing_driver_fields": ["state", "impact_type", "imaging"]},
            ),
            rule=None,
            judgment=JudgmentAggregate(
                median_tier=2, median_liability_pct=70, tier_spread=2, liability_spread=40
            ),
        )
        assert sparse["width"] > rich["width"]
        assert sparse["confidence"] == "low"
        rich_ratio = rich["gross_max"] / rich["gross_min"]
        sparse_ratio = sparse["gross_max"] / max(sparse["gross_min"], 1)
        assert sparse_ratio > rich_ratio

    def test_adversarial_floor_pulls_low_and_feeds_reducers(self):
        adversarial = AdversarialSummary(
            lowest_defensible_pct_of_specials=60,
            attack_arguments=[
                {"category": "documentation", "argument": "Bills are unverified."},
                {"category": "causation", "argument": "Late first treatment."},
            ],
        )
        with_adv = self._assemble(extraction(**REAR_END_DOCUMENTED), adversarial=adversarial)
        without = self._assemble(extraction(**REAR_END_DOCUMENTED))
        assert with_adv["gross_min"] < without["gross_min"]
        assert with_adv["reducers"] == ["Bills are unverified.", "Late first treatment."]

    def test_policy_cap_limits_both_bounds(self):
        capped_case = dict(REAR_END_DOCUMENTED)
        capped_case["liability"] = {
            **REAR_END_DOCUMENTED["liability"],
            "defendant": {
                "policy_limits_known": True,
                "policy_limits_amount": money(25_000, True),
            },
        }
        result = self._assemble(extraction(**capped_case))
        assert result["gross_max"] <= 25_000

    def test_comps_anchor_moves_the_range(self):
        comps = CompsSummary(
            comps=[{"amount": 150_000, "source_quality": "published_verdict"}]
        )
        anchored = self._assemble(extraction(**REAR_END_DOCUMENTED), comps=comps)
        plain = self._assemble(extraction(**REAR_END_DOCUMENTED))
        assert anchored["gross_max"] > plain["gross_max"]

    def test_unverified_jurisdiction_extends_disclaimer(self):
        reviewed = self._assemble(extraction(**REAR_END_DOCUMENTED), rule=Rule(needs_review=False))
        pending = self._assemble(extraction(**REAR_END_DOCUMENTED), rule=Rule(needs_review=True))
        assert "pending attorney verification" not in reviewed["disclaimer"]
        assert "pending attorney verification" in pending["disclaimer"]


class TestAssembleGated:
    def test_gated_result_zeroes_figures_and_keeps_warnings(self):
        x = extraction(
            meta={"incident_date": "2020-01-01", "state": "TN"},
            gates={"government_defendant": True},
        )
        gate = evaluate_gates(x, Rule(state_name="Tennessee", sol_years_pi=1.0),
                              __import__("datetime").date(2026, 7, 12))
        assert gate.blocked
        result = assemble_gated(x, Rule(), gate)
        assert result["gated"]["code"] == "sol_expired"
        assert result["gross_min"] == result["gross_max"] == 0
        assert any(w["code"] == "notice_of_claim" for w in result["warnings"])
        assert result["disclaimer"].startswith(assembly.DISCLAIMER[:40])
