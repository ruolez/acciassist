"""Stage 6 — assembly: every dollar figure is computed here, in code.

Inputs are judgments (extraction facts, sampled severity tier and liability
percentage, an adversarial floor expressed as a percent of specials, optional
comparable results) — never model-produced dollars. All constants below are
estimation heuristics, not legal rules.
"""

from dataclasses import dataclass, field

from app.services.estimate_pipeline.canonical import CanonicalExtraction
from app.services.estimate_pipeline.gates import GateResult, GateWarning

# ── Heuristic constants — attorney review recommended ──────────────────

# General-damages multiplier applied to weighted medical specials, by
# severity tier (1 = soft tissue, 5 = permanent/catastrophic).
TIER_MULTIPLIERS: dict[int, tuple[float, float]] = {
    1: (1.5, 2.5),
    2: (2.0, 3.5),
    3: (3.0, 4.5),
    4: (4.0, 6.0),
    5: (5.0, 8.0),
}
UNDOCUMENTED_MEDICAL_WEIGHT = 0.5
# Typical billed medical by treatment level, assumed ONLY when the intake
# captured no medical-bill amount but treatment clearly happened. Weighted
# like undocumented bills and disclosed to the patient as a footnote.
ASSUMED_MEDICAL_BY_TREATMENT: dict[str, float] = {
    "er_only": 3000.0,
    "conservative_care": 6000.0,
    "pain_management": 12000.0,
    "injections": 20000.0,
    "surgery_recommended_written": 30000.0,
    "surgery_performed": 75000.0,
}
FUTURE_CARE_WEIGHT_IN_WRITING = 1.0
FUTURE_CARE_WEIGHT_CLAIMED = 0.3
# (employment group, documented) -> weight; cash wages are excluded entirely.
WAGE_WEIGHTS: dict[tuple[str, bool], float] = {
    ("w2", True): 1.0,
    ("w2", False): 0.5,
    ("self_employed_1099", True): 0.75,
    ("self_employed_1099", False): 0.35,
    ("other", True): 0.5,
    ("other", False): 0.25,
}
OUT_OF_POCKET_UNDOCUMENTED_WEIGHT = 0.5
# Firm's cost to pursue, by severity tier.
CASE_COSTS_BY_TIER: dict[int, tuple[int, int]] = {
    1: (1500, 5000),
    2: (1500, 5000),
    3: (5000, 15000),
    4: (15000, 50000),
    5: (25000, 75000),
}
# Estimated lien as a share of documented medical, by payor.
LIEN_PCT_BY_PAYOR: dict[str, float] = {
    "medicare": 0.50,
    "medicaid": 0.35,
    "private": 0.40,
    "erisa_selffunded": 0.60,
    "tricare_va": 0.40,
    "medpay_pip": 0.20,
    "letter_of_protection": 1.00,
    "none_self_pay": 0.0,
    "unknown": 0.40,
}
LIEN_CAP_PCT_OF_GROSS = 0.40
# In a contributory-negligence state, any admitted fault above this percent
# is treated as potentially claim-barring.
CONTRIBUTORY_FAULT_EPSILON = 5.0
CONTRIBUTORY_SURVIVAL_FACTOR = 0.25
# Range-width formula weights (see range_width).
WIDTH_PER_TIER_SPREAD = 0.08
WIDTH_PER_LIABILITY_SPREAD = 1 / 200
WIDTH_PER_MISSING_DRIVER = 0.05
WIDTH_MISSING_CAP = 8
WIDTH_MIN, WIDTH_MAX = 0.05, 0.60
# Soft geometric pull toward the comps anchor: center^0.7 * comps^0.3.
COMPS_CENTER_EXPONENT = 0.7
COMPS_ANCHOR_EXPONENT = 0.3
COMPS_SANITY_RATIO = (0.2, 5.0)
COMPS_SOURCE_WEIGHTS = {"published_verdict": 1.0, "news": 0.6, "firm_marketing": 0.3}
COMPS_MAX_AMOUNT = 50_000_000

DISCLAIMER = (
    "This is an automated, preliminary estimate based only on the answers provided. "
    "It is not legal advice, it does not create an attorney-client relationship, and "
    "real case values vary widely with facts, documentation, insurance limits, and "
    "venue. An attorney's review is the only way to get a dependable valuation."
)
UNVERIFIED_JURISDICTION_NOTE = (
    " State-specific legal parameters used here are compiled from public sources and "
    "are pending attorney verification."
)


# ── Inputs from the model stages ────────────────────────────────────────


@dataclass
class JudgmentAggregate:
    median_tier: int
    median_liability_pct: float
    tier_spread: int
    liability_spread: float
    swing_facts: list[str] = field(default_factory=list)


@dataclass
class AdversarialSummary:
    lowest_defensible_pct_of_specials: float
    low_rationale: str = ""
    attack_arguments: list[dict] = field(default_factory=list)  # {category, argument}


@dataclass
class CompsSummary:
    comps: list[dict] = field(default_factory=list)

    def weighted_median(self) -> float | None:
        """Median comp amount, weighted by source quality (published verdicts
        count most, firm-marketing pages least)."""
        entries = sorted(
            (
                (float(c["amount"]), COMPS_SOURCE_WEIGHTS.get(c.get("source_quality"), 0.3))
                for c in self.comps
                if 0 < float(c.get("amount") or 0) <= COMPS_MAX_AMOUNT
            ),
        )
        total = sum(w for _, w in entries)
        if total <= 0:
            return None
        acc = 0.0
        for amount, weight in entries:
            acc += weight
            if acc >= total / 2:
                return amount
        return entries[-1][0]


# ── Pure computation steps ───────────────────────────────────────────────


@dataclass
class Specials:
    weighted_medical: float
    weighted_future_care: float
    weighted_wages: float
    weighted_out_of_pocket: float
    documented_medical: float
    # Non-zero when no bill amount was captured and a typical amount for the
    # treatment level was assumed instead (disclosed via result footnote).
    assumed_medical: float = 0.0
    flags: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return (
            self.weighted_medical
            + self.weighted_future_care
            + self.weighted_wages
            + self.weighted_out_of_pocket
        )


def _wage_group(employment_type: str | None) -> str:
    if employment_type in ("w2", "self_employed_1099", "cash_unreported"):
        return employment_type
    return "other"


def weight_specials(x: CanonicalExtraction) -> Specials:
    econ = x.economic
    medical = econ.medical_billed_to_date.amount or 0.0
    weighted_medical = medical * (
        1.0 if econ.medical_billed_to_date.documented else UNDOCUMENTED_MEDICAL_WEIGHT
    )
    assumed_medical = 0.0
    if medical == 0:
        ladder = x.injury.treatment_ladder.highest_reached
        if ladder in ASSUMED_MEDICAL_BY_TREATMENT:
            assumed_medical = ASSUMED_MEDICAL_BY_TREATMENT[ladder]
        elif x.injury.time_to_first_treatment is not None:
            assumed_medical = ASSUMED_MEDICAL_BY_TREATMENT["er_only"]
        weighted_medical = assumed_medical * UNDOCUMENTED_MEDICAL_WEIGHT

    future = econ.future_medical.amount or 0.0
    in_writing = (
        x.injury.treatment_ladder.future_care_in_writing is True
        or econ.future_medical.documented
    )
    weighted_future = future * (
        FUTURE_CARE_WEIGHT_IN_WRITING if in_writing else FUTURE_CARE_WEIGHT_CLAIMED
    )

    flags: list[str] = []
    wages = econ.lost_wages.claimed.amount or 0.0
    group = _wage_group(econ.lost_wages.employment_type)
    documented_wages = econ.lost_wages.verifiable is True or econ.lost_wages.claimed.documented
    if group == "cash_unreported":
        weighted_wages = 0.0
        if wages > 0:
            flags.append(
                "Claimed lost wages from unreported cash income were excluded: they are "
                "routinely rejected without tax records."
            )
    else:
        weighted_wages = wages * WAGE_WEIGHTS[(group, documented_wages)]

    oop = econ.out_of_pocket.amount or 0.0
    weighted_oop = oop * (
        1.0 if econ.out_of_pocket.documented else OUT_OF_POCKET_UNDOCUMENTED_WEIGHT
    )

    return Specials(
        weighted_medical=weighted_medical,
        weighted_future_care=weighted_future,
        weighted_wages=weighted_wages,
        weighted_out_of_pocket=weighted_oop,
        documented_medical=medical if econ.medical_billed_to_date.documented else 0.0,
        assumed_medical=assumed_medical,
        flags=flags,
    )


def general_damages(
    weighted_medical: float, tier: int, noneconomic_cap: int | None
) -> tuple[float, float]:
    lo_mult, hi_mult = TIER_MULTIPLIERS[min(max(tier, 1), 5)]
    low, high = weighted_medical * lo_mult, weighted_medical * hi_mult
    if noneconomic_cap is not None:
        low, high = min(low, noneconomic_cap), min(high, noneconomic_cap)
    return low, high


def apply_liability(
    low: float, high: float, defendant_pct: float, comparative_rule: str | None
) -> tuple[float, float, list[GateWarning]]:
    fault = 100.0 - defendant_pct
    factor = defendant_pct / 100.0
    warnings: list[GateWarning] = []
    if comparative_rule == "contributory":
        if fault >= CONTRIBUTORY_FAULT_EPSILON:
            warnings.append(
                GateWarning(
                    "contributory_bar",
                    "caution",
                    "This state follows contributory negligence: being found even "
                    "slightly at fault can bar recovery entirely. The estimate is "
                    "discounted heavily for that risk.",
                )
            )
            return 0.0, high * CONTRIBUTORY_SURVIVAL_FACTOR, warnings
        return low, high, warnings
    if comparative_rule == "modified_50" and fault >= 50:
        warnings.append(
            GateWarning(
                "comparative_bar",
                "caution",
                "The facts suggest you may be found 50% or more at fault, which bars "
                "recovery under this state's comparative-negligence rule.",
            )
        )
        return 0.0, 0.0, warnings
    if comparative_rule == "modified_51" and fault >= 51:
        warnings.append(
            GateWarning(
                "comparative_bar",
                "caution",
                "The facts suggest you may be found more than 50% at fault, which bars "
                "recovery under this state's comparative-negligence rule.",
            )
        )
        return 0.0, 0.0, warnings
    return low * factor, high * factor, warnings


def apply_comps_anchor(low: float, high: float, comps_median: float | None) -> tuple[float, float]:
    center = (low + high) / 2
    if comps_median is None or center <= 0:
        return low, high
    ratio = comps_median / center
    if not (COMPS_SANITY_RATIO[0] < ratio < COMPS_SANITY_RATIO[1]):
        return low, high
    new_center = (center**COMPS_CENTER_EXPONENT) * (comps_median**COMPS_ANCHOR_EXPONENT)
    scale = new_center / center
    return low * scale, high * scale


def count_missing_drivers(x: CanonicalExtraction) -> int:
    """Nulls and undocumented dollars on high-signal fields widen the range."""
    count = len(
        {f.strip().lower() for f in x.extraction_notes.missing_driver_fields if f.strip()}
    )
    for money in (
        x.economic.medical_billed_to_date,
        x.economic.future_medical,
        x.economic.lost_wages.claimed,
    ):
        if (money.amount or 0) > 0 and not money.documented:
            count += 1
    if x.meta.state is None:
        count += 2
    if x.injury.objective_finding.status in ("unknown", "imaging_pending"):
        count += 1
    return count


def range_width(tier_spread: int, liability_spread: float, missing_driver_count: int) -> float:
    w = (
        WIDTH_PER_TIER_SPREAD * tier_spread
        + WIDTH_PER_LIABILITY_SPREAD * liability_spread
        + WIDTH_PER_MISSING_DRIVER * min(missing_driver_count, WIDTH_MISSING_CAP)
    )
    return min(max(w, WIDTH_MIN), WIDTH_MAX)


def apply_adversarial_floor(
    low: float, adversarial_pct: float | None, specials_total: float
) -> float:
    """Blend the floor toward the defense adjuster's lowest defensible number
    (a percent of weighted specials) when it undercuts ours."""
    if adversarial_pct is None:
        return low
    adv_low = max(specials_total * adversarial_pct / 100.0, 0.0)
    return (low + adv_low) / 2 if adv_low < low else low


def policy_cap(x: CanonicalExtraction) -> float | None:
    d = x.liability.defendant
    if d.policy_limits_known is not True or not d.policy_limits_amount.amount:
        return None
    cap = d.policy_limits_amount.amount
    if d.claimant_um_uim == "yes" and d.claimant_um_uim_limits.amount:
        cap += d.claimant_um_uim_limits.amount
    return cap


def round_estimate(n: float) -> int:
    n = max(n, 0.0)
    step = 250 if n < 10_000 else 500 if n < 50_000 else 1000
    return int(round(n / step) * step)


def derive_confidence(width: float, missing_driver_count: int) -> str:
    if width < 0.15 and missing_driver_count <= 1:
        return "high"
    if width < 0.30 and missing_driver_count <= 4:
        return "medium"
    return "low"


# ── Narrative pieces (code-selected, cited to answers) ──────────────────

_DRIVER_RULES: list = [
    (
        lambda x, s: x.injury.treatment_ladder.highest_reached == "surgery_performed",
        "Surgery was performed — the strongest single driver of case value.",
    ),
    (
        lambda x, s: x.injury.treatment_ladder.highest_reached == "surgery_recommended_written",
        "A surgeon recommended surgery in writing, which insurers value far above a "
        "verbal mention.",
    ),
    (
        lambda x, s: (x.injury.treatment_ladder.impairment_rating_pct or 0) > 0,
        "A permanent impairment rating has been assigned.",
    ),
    (
        lambda x, s: x.injury.objective_finding.status == "imaging_positive",
        "Imaging shows an objective finding, which separates this claim from "
        "pain-only cases.",
    ),
    (
        lambda x, s: x.liability.mva is not None
        and x.liability.mva.impact_type == "rear_ended",
        "You were rear-ended — liability in rear-end collisions is close to automatic.",
    ),
    (
        lambda x, s: x.liability.evidence.citation_issued_to == "other_party",
        "The other party was cited by police, which strongly supports liability.",
    ),
    (
        lambda x, s: x.liability.evidence.admission_of_fault == "recorded",
        "The other party admitted fault on record.",
    ),
    (
        lambda x, s: x.liability.premises is not None
        and x.liability.premises.notice is not None
        and x.liability.premises.notice.theory
        in ("actual_defendant_created", "actual_prior_complaints"),
        "There is evidence the property owner knew about (or created) the hazard — "
        "the make-or-break issue in premises cases.",
    ),
    (
        lambda x, s: s.documented_medical >= 10_000,
        "Substantial documented medical bills anchor the damages calculation.",
    ),
    (
        lambda x, s: x.liability.defendant.type in ("commercial_vehicle", "chain_national")
        or x.liability.defendant.acting_in_course_of_employment is True,
        "A commercial defendant is involved; commercial policy limits are typically "
        "many times higher than personal ones.",
    ),
    (
        lambda x, s: x.liability.mva is not None
        and x.liability.mva.property_damage_level in ("severe", "totaled"),
        "Severe vehicle damage makes the injury claim far harder for the defense to "
        "minimize.",
    ),
]

_REDUCER_RULES: list = [
    (
        lambda x: x.injury.treatment_gap.duration_bucket in ("30_to_59_days", "60_plus_days"),
        "A 30+ day gap in treatment — adjusters use this to argue the injury was minor "
        "or unrelated.",
    ),
    (
        lambda x: x.injury.preexisting.same_body_part_prior_injury is True,
        "A prior injury to the same body part invites a causation defense.",
    ),
    (
        lambda x: x.liability.mva is not None
        and x.liability.mva.property_damage_level in ("none_visible", "minor_cosmetic"),
        "Low visible vehicle damage — the defense's most effective argument against "
        "soft-tissue claims.",
    ),
    (
        lambda x: x.injury.objective_finding.status in ("imaging_normal", "no_imaging"),
        "No objective imaging finding; pain-only claims are valued far lower.",
    ),
    (
        lambda x: x.economic.lost_wages.employment_type == "cash_unreported",
        "Undocumented cash income cannot support a wage-loss claim.",
    ),
    (
        lambda x: x.injury.preexisting.prior_claims_count == "two_plus",
        "Multiple prior injury claims raise credibility questions insurers exploit.",
    ),
]


def top_drivers(x: CanonicalExtraction, specials: Specials, limit: int = 3) -> list[str]:
    return [text for cond, text in _DRIVER_RULES if cond(x, specials)][:limit]


def fallback_reducers(x: CanonicalExtraction, limit: int = 3) -> list[str]:
    return [text for cond, text in _REDUCER_RULES if cond(x)][:limit]


_IMPROVEMENT_CHECKS: list = [
    (
        lambda x: x.injury.treatment_ladder.highest_reached == "none"
        or x.injury.time_to_first_treatment == "never",
        "Seeing a doctor about your injuries — documented treatment is the foundation "
        "of a claim and unlocks everything else.",
    ),
    (
        lambda x: (x.economic.medical_billed_to_date.amount or 0) > 0
        and not x.economic.medical_billed_to_date.documented,
        "Copies of your medical bills or an itemized billing statement.",
    ),
    (
        lambda x: (x.economic.lost_wages.claimed.amount or 0) > 0
        and x.economic.lost_wages.verifiable is not True,
        "Proof of lost wages: pay stubs, an employer letter, or tax returns.",
    ),
    (
        lambda x: x.injury.treatment_ladder.future_care_recommended is True
        and x.injury.treatment_ladder.future_care_in_writing is not True,
        "A written cost estimate for recommended future care from your provider.",
    ),
    (
        lambda x: x.injury.objective_finding.status == "imaging_pending",
        "The written radiology report from your imaging, once it is read.",
    ),
    (
        lambda x: x.injury.objective_finding.status == "no_imaging",
        "Imaging (X-ray/MRI) if a doctor orders it — a documented finding is the "
        "single biggest driver of case value.",
    ),
    (
        lambda x: x.meta.state is None,
        "The state (and county) where the incident happened.",
    ),
    (
        lambda x: x.liability.evidence.police_report is not True
        and x.meta.case_type == "motor_vehicle",
        "The police report number, if a report was made.",
    ),
]


def improvements(x: CanonicalExtraction, limit: int = 5) -> list[str]:
    items = [text for cond, text in _IMPROVEMENT_CHECKS if cond(x)]
    return items[:limit]


# ── Entry points ─────────────────────────────────────────────────────────


def _warning_dict(w: GateWarning) -> dict:
    return {
        "code": w.code,
        "severity": w.severity,
        "message": w.message,
        "deadline": w.deadline.isoformat() if w.deadline else None,
    }


def _disclaimer(rule) -> str:
    text = DISCLAIMER
    if rule is not None and getattr(rule, "needs_review", False):
        text += UNVERIFIED_JURISDICTION_NOTE
    return text


def assemble_gated(x: CanonicalExtraction, rule, gate: GateResult) -> dict:
    return {
        "gated": {"code": gate.code, "title": gate.title, "explanation": gate.explanation},
        "gross_min": 0,
        "gross_max": 0,
        "net_min": 0,
        "net_max": 0,
        "case_cost_min": 0,
        "case_cost_max": 0,
        "fee_pct": None,
        "width": None,
        "confidence": "low",
        "summary": gate.explanation,
        "drivers": [],
        "reducers": [],
        "improvements": improvements(x),
        "warnings": [_warning_dict(w) for w in gate.warnings],
        "disclaimer": _disclaimer(rule),
        "trace": {"gate_code": gate.code},
    }


def compute_net(
    gross: float, fee_pct: float, case_costs: float, payor_type: str | None,
    documented_medical: float,
) -> float:
    lien_pct = LIEN_PCT_BY_PAYOR.get(payor_type or "unknown", LIEN_PCT_BY_PAYOR["unknown"])
    lien = min(lien_pct * documented_medical, LIEN_CAP_PCT_OF_GROSS * gross)
    return max(gross * (1 - fee_pct / 100.0) - case_costs - lien, 0.0)


def assemble(
    x: CanonicalExtraction,
    rule,
    gate: GateResult,
    judgment: JudgmentAggregate,
    adversarial: AdversarialSummary | None,
    comps: CompsSummary | None,
    fee_pct: float,
) -> dict:
    trace: dict = {}
    tier = min(max(judgment.median_tier, 1), 5)

    specials = weight_specials(x)
    trace["specials"] = {
        "weighted_medical": specials.weighted_medical,
        "weighted_future_care": specials.weighted_future_care,
        "weighted_wages": specials.weighted_wages,
        "weighted_out_of_pocket": specials.weighted_out_of_pocket,
        "documented_medical": specials.documented_medical,
        "assumed_medical": specials.assumed_medical,
        "total": specials.total,
        "flags": specials.flags,
    }

    cap = rule.noneconomic_cap if rule is not None else None
    gen_low, gen_high = general_damages(specials.weighted_medical, tier, cap)
    trace["general_damages"] = {"tier": tier, "low": gen_low, "high": gen_high, "cap": cap}

    low, high = specials.total + gen_low, specials.total + gen_high
    trace["gross_before_liability"] = {"low": low, "high": high}

    comparative_rule = rule.comparative_rule if rule is not None else None
    low, high, liability_warnings = apply_liability(
        low, high, judgment.median_liability_pct, comparative_rule
    )
    trace["after_liability"] = {
        "low": low,
        "high": high,
        "defendant_pct": judgment.median_liability_pct,
        "rule": comparative_rule,
    }

    comps_median = comps.weighted_median() if comps is not None else None
    low, high = apply_comps_anchor(low, high, comps_median)
    trace["comps_anchor"] = {"weighted_median": comps_median, "low": low, "high": high}

    missing = count_missing_drivers(x)
    width = range_width(judgment.tier_spread, judgment.liability_spread, missing)
    low, high = low * (1 - width), high * (1 + width)
    trace["width"] = {
        "value": width,
        "tier_spread": judgment.tier_spread,
        "liability_spread": judgment.liability_spread,
        "missing_driver_count": missing,
    }

    adv_pct = adversarial.lowest_defensible_pct_of_specials if adversarial else None
    low = apply_adversarial_floor(low, adv_pct, specials.total)
    trace["adversarial_floor"] = {"pct_of_specials": adv_pct, "low": low}

    cap_amount = policy_cap(x)
    if cap_amount is not None:
        low, high = min(low, cap_amount), min(high, cap_amount)
    trace["policy_cap"] = cap_amount

    gross_min, gross_max = round_estimate(low), round_estimate(max(high, low))
    cost_low, cost_high = CASE_COSTS_BY_TIER[tier]
    payor = x.economic.liens.payor_type
    net_min = round_estimate(
        compute_net(gross_min, fee_pct, cost_high, payor, specials.documented_medical)
    )
    net_max = round_estimate(
        compute_net(gross_max, fee_pct, cost_low, payor, specials.documented_medical)
    )
    net_min = min(net_min, net_max)

    confidence = derive_confidence(width, missing)
    warnings = [*gate.warnings, *liability_warnings]

    reducers = [a["argument"] for a in (adversarial.attack_arguments if adversarial else [])]
    reducers = [r for r in reducers if r][:3] or fallback_reducers(x)

    summary = (
        f"Computed from severity tier {tier} with {judgment.median_liability_pct:.0f}% "
        f"defendant liability across sampled evaluations, "
        f"${specials.total:,.0f} in weighted documented losses, and "
        f"{missing} missing or undocumented high-signal facts widening the range by "
        f"±{width:.0%}."
    )

    footnotes = []
    if specials.assumed_medical > 0:
        footnotes.append(
            f"* No medical bill amounts were provided, so this estimate assumes roughly "
            f"${specials.assumed_medical:,.0f} in medical bills — typical for the "
            "treatment described. Actual bills can move this range substantially."
        )

    return {
        "gated": None,
        "gross_min": gross_min,
        "gross_max": gross_max,
        "net_min": net_min,
        "net_max": net_max,
        "case_cost_min": cost_low,
        "case_cost_max": cost_high,
        "fee_pct": fee_pct,
        "width": width,
        "confidence": confidence,
        "summary": summary,
        "drivers": top_drivers(x, specials),
        "reducers": reducers,
        "improvements": improvements(x),
        "warnings": [_warning_dict(w) for w in warnings],
        "footnotes": footnotes,
        "disclaimer": _disclaimer(rule),
        "trace": trace,
    }
