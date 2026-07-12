"""Canonical Stage-1 extraction contract.

``EXTRACTION_JSON_SCHEMA`` is what the model is forced to fill (OpenRouter
strict structured output: every object lists all keys in ``required`` and
sets ``additionalProperties: false``; optionality is expressed as
type-unions with null). The Pydantic models mirror it tolerantly for
parsing: they ignore extras, default missing branches, normalize state
names, and clamp numerics — so a fallback free-text reply still has a
chance of validating.

The extraction is FACTS ONLY. Subjective judgments (severity tier,
liability percentage) belong to the sampled judgment stage; deterministic
consequences (gates, math) belong to code.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.services.estimate_pipeline.jurisdiction_data import (
    STATE_CODES,
    STATE_NAMES_TO_CODES,
)

# ── JSON-schema builders (guarantee strict-mode invariants) ────────────


def _obj(props: dict, nullable: bool = False) -> dict:
    return {
        "type": ["object", "null"] if nullable else "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


def _enum(*values: str, description: str | None = None) -> dict:
    schema: dict = {"type": ["string", "null"], "enum": [*values, None]}
    if description:
        schema["description"] = description
    return schema


def _null(type_: str, description: str | None = None) -> dict:
    schema: dict = {"type": [type_, "null"]}
    if description:
        schema["description"] = description
    return schema


_STR_ARRAY = {"type": "array", "items": {"type": "string"}}

_CONFIDENCE = {
    "type": "string",
    "enum": ["high", "medium", "low", "absent"],
    "description": (
        "high = explicit answer. medium = clear but qualitative. "
        "low = vague, hedged, or derived from adjacent answers. absent = not answered."
    ),
}

_MONEY = _obj(
    {
        "amount": _null("number"),
        "documented": {
            "type": "boolean",
            "description": (
                "TRUE only if the respondent affirmatively indicated documentation exists "
                "(bill, statement, pay stub, written provider estimate). Absence of an "
                "answer is FALSE, never TRUE."
            ),
        },
        "confidence": _CONFIDENCE,
        "source_field": _null(
            "string", "Questionnaire slug this came from, e.g. 'medical_bills_amount'"
        ),
    }
)

_FLAG = _obj(
    {
        "code": {"type": "string"},
        "severity": {"type": "string", "enum": ["blocking", "major", "minor", "info"]},
        "explanation": {"type": "string"},
    }
)

EXTRACTION_SCHEMA_NAME = "case_extraction"

EXTRACTION_JSON_SCHEMA = {
    **_obj(
        {
            "meta": _obj(
                {
                    "case_type": {
                        "type": "string",
                        "enum": ["motor_vehicle", "slip_trip_fall", "other", "out_of_scope"],
                    },
                    "state": _null(
                        "string",
                        "Two-letter USPS code for the US state where the incident happened; "
                        "null if not stated.",
                    ),
                    "county": _null("string"),
                    "incident_date": _null("string", "ISO date YYYY-MM-DD; null if not stated"),
                    "claimant_age": _null("integer"),
                    "already_represented": _null("boolean"),
                }
            ),
            "gates": _obj(
                {
                    "release_signed": _null("boolean"),
                    "fatality_involved": _null("boolean"),
                    "workplace_injury": _null(
                        "boolean",
                        "True if the injury occurred in the course of the claimant's work "
                        "(likely workers'-comp exclusive remedy).",
                    ),
                    "government_defendant": _null("boolean"),
                    "claimant_status_premises": _enum(
                        "invitee_customer",
                        "licensee_guest",
                        "tenant",
                        "employee",
                        "delivery",
                        "trespasser",
                        "unknown",
                    ),
                }
            ),
            "injury": _obj(
                {
                    "body_parts": _STR_ARRAY,
                    "time_to_first_treatment": _enum(
                        "same_day", "within_72h", "3_to_14_days", "over_14_days",
                        "never", "unknown",
                    ),
                    "objective_finding": _obj(
                        {
                            "status": {
                                "type": "string",
                                "enum": [
                                    "imaging_positive", "imaging_normal", "imaging_pending",
                                    "no_imaging", "unknown",
                                ],
                                "description": (
                                    "imaging_positive requires a stated finding (fracture, "
                                    "herniation, tear). 'Doctor said it looked bad' is NOT "
                                    "imaging_positive."
                                ),
                            },
                            "finding_verbatim": _null(
                                "string",
                                "Quote the respondent's words. Do not medicalize or upgrade "
                                "the language.",
                            ),
                            "confidence": _CONFIDENCE,
                        }
                    ),
                    "treatment_ladder": _obj(
                        {
                            "highest_reached": {
                                "type": "string",
                                "enum": [
                                    "none", "er_only", "conservative_care", "pain_management",
                                    "injections", "surgery_recommended_written",
                                    "surgery_performed",
                                ],
                                "description": (
                                    "Ordered ladder. 'Doctor mentioned surgery' is NOT "
                                    "surgery_recommended_written — a written recommendation only."
                                ),
                            },
                            "modalities": _STR_ARRAY,
                            "still_treating": _null("boolean"),
                            "future_care_recommended": _null("boolean"),
                            "future_care_in_writing": _null("boolean"),
                            "impairment_rating_pct": _null("number"),
                        }
                    ),
                    "treatment_gap": _obj(
                        {
                            "present": _null("boolean"),
                            "duration_bucket": _enum("none", "30_to_59_days", "60_plus_days",
                                                     "unknown"),
                            "stated_reason": _null("string"),
                            "reason_mitigating": _null(
                                "boolean",
                                "TRUE if the stated reason is credible and non-volitional "
                                "(no insurance, provider unavailable).",
                            ),
                        }
                    ),
                    "preexisting": _obj(
                        {
                            "same_body_part_prior_injury": _null("boolean"),
                            "treating_within_12mo": _null("boolean"),
                            "prior_claims_count": _enum("none", "one", "two_plus", "unknown"),
                            "prior_workers_comp": _null("boolean"),
                        }
                    ),
                }
            ),
            "economic": _obj(
                {
                    "medical_billed_to_date": _MONEY,
                    "future_medical": _MONEY,
                    "out_of_pocket": _MONEY,
                    "lost_wages": _obj(
                        {
                            "claimed": _MONEY,
                            "days_missed": _null("number"),
                            "employment_type": _enum(
                                "w2", "self_employed_1099", "cash_unreported", "unemployed",
                                "retired", "student", "unknown",
                            ),
                            "verifiable": _null(
                                "boolean",
                                "Pay stubs / employer letter / tax return exist. "
                                "Cash-unreported income: set FALSE and raise a flag.",
                            ),
                            "earning_capacity_impaired": _null("boolean"),
                        }
                    ),
                    "liens": _obj(
                        {
                            "payor_type": _enum(
                                "none_self_pay", "private", "medicare", "medicaid",
                                "erisa_selffunded", "tricare_va", "medpay_pip",
                                "letter_of_protection", "unknown",
                            ),
                            "lien_asserted": _null("boolean"),
                            "lien_amount": _MONEY,
                            "treating_on_lop": _null("boolean"),
                        }
                    ),
                }
            ),
            "liability": _obj(
                {
                    "self_reported_fault": _enum(
                        "not_at_all", "slightly", "partly", "mostly", "unsure",
                        description="The claimant's own words about their share of fault — "
                        "report, do not judge.",
                    ),
                    "evidence": _obj(
                        {
                            "police_report": _null("boolean"),
                            "citation_issued_to": _enum("other_party", "claimant", "both",
                                                        "neither", "unknown"),
                            "admission_of_fault": _enum("recorded", "verbal", "none", "unknown"),
                            "independent_witnesses": _null("integer"),
                            "photos_of_scene": _null("boolean"),
                            "incident_report_same_day": _null("boolean"),
                            "surveillance_exists": _null("boolean"),
                            "surveillance_preservation_sent": _null("boolean"),
                        }
                    ),
                    "mva": _obj(
                        {
                            "impact_type": _enum(
                                "rear_ended", "t_bone_other_ran_light", "head_on", "sideswipe",
                                "left_turn", "claimant_struck_other", "other",
                            ),
                            "claimant_role": _enum("driver", "passenger", "pedestrian",
                                                   "cyclist"),
                            "property_damage_level": _enum(
                                "none_visible", "minor_cosmetic", "moderate", "severe",
                                "totaled", "unknown",
                                description="DRIVER field. Low property damage is the "
                                "defense's strongest soft-tissue argument.",
                            ),
                            "vehicle_drivable_after": _null("boolean"),
                            "airbags_deployed": _null("boolean"),
                            "seatbelt_worn": _null("boolean"),
                        },
                        nullable=True,
                    ),
                    "premises": _obj(
                        {
                            "location_type": _null("string"),
                            "hazard_type": _null("string"),
                            "notice": _obj(
                                {
                                    "theory": {
                                        "type": "string",
                                        "enum": [
                                            "actual_defendant_created",
                                            "actual_prior_complaints",
                                            "constructive_duration",
                                            "none_established",
                                        ],
                                        "description": (
                                            "none_established is the correct answer far more "
                                            "often than claimants expect. Do not invent notice."
                                        ),
                                    },
                                    "hazard_duration": _enum("just_occurred", "minutes",
                                                             "hours", "days_or_longer",
                                                             "unknown"),
                                    "evidentiary_basis": {
                                        "type": "string",
                                        "description": (
                                            "How is duration KNOWN? Witness, dried edges, "
                                            "tracked-through debris, prior complaint. "
                                            "'Claimant assumes' is not a basis."
                                        ),
                                    },
                                },
                                nullable=True,
                            ),
                            "warning_present": _null("boolean"),
                            "open_and_obvious": _enum("hidden", "partially_visible",
                                                      "plainly_visible", "unknown"),
                            "claimant_distraction": _null("string"),
                            "footwear": _null("string"),
                        },
                        nullable=True,
                    ),
                    "defendant": _obj(
                        {
                            "type": _enum(
                                "individual", "commercial_vehicle", "business_entity",
                                "chain_national", "government", "landlord", "unknown",
                            ),
                            "acting_in_course_of_employment": _null("boolean"),
                            "policy_limits_known": _null("boolean"),
                            "policy_limits_amount": _MONEY,
                            "claimant_um_uim": _enum("yes", "no", "unsure"),
                            "claimant_um_uim_limits": _MONEY,
                        }
                    ),
                }
            ),
            "human_damages": _obj(
                {
                    "activities_lost": _STR_ARRAY,
                    "visible_scarring": _null("boolean"),
                    "psychological_impact": _null("boolean"),
                    "psychological_treating": _null("boolean"),
                    "caregiving_impairment": _null("boolean"),
                    "specificity_score": _null(
                        "number",
                        "0-1: how concrete are the descriptions? 'Can't lift my daughter "
                        "into her car seat' = high; 'a lot of pain' = low.",
                    ),
                }
            ),
            "extraction_notes": _obj(
                {
                    "flags": {"type": "array", "items": _FLAG},
                    "missing_driver_fields": {
                        **_STR_ARRAY,
                        "description": (
                            "High-signal facts left unanswered (state, imaging status, bill "
                            "amounts, liability evidence). Directly widens the output range."
                        ),
                    },
                    "internal_inconsistencies": {
                        **_STR_ARRAY,
                        "description": (
                            "e.g. claims 6 months of PT but $900 in bills. Report, do not "
                            "resolve."
                        ),
                    },
                    "model_refusals": {
                        **_STR_ARRAY,
                        "description": (
                            "Fields you declined to populate for lack of basis. An empty "
                            "list on a sparse questionnaire signals confabulation."
                        ),
                    },
                }
            ),
        }
    ),
    "title": "PI Case Extraction — Stage 1 Output",
    "description": (
        "Structured extraction from a claimant questionnaire. Fill this and NOTHING else: "
        "no case valuation, no multipliers, no dollar figures beyond what was reported."
    ),
}


# ── Tolerant Pydantic mirrors ──────────────────────────────────────────


def _clean_token(v: object) -> object:
    """Lowercase/strip string tokens so 'Unknown' or ' w2 ' still validate."""
    if isinstance(v, str):
        v = v.strip().lower()
        return v or None
    return v


Token = BeforeValidator(_clean_token)

Confidence = Annotated[Literal["high", "medium", "low", "absent"], Token]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Money(_Model):
    amount: float | None = None
    documented: bool = False
    confidence: Confidence = "absent"
    source_field: str | None = None

    @field_validator("amount")
    @classmethod
    def _non_negative(cls, v: float | None) -> float | None:
        if v is None:
            return None
        return max(float(v), 0.0)


class ExtractionFlag(_Model):
    code: str
    severity: Annotated[Literal["blocking", "major", "minor", "info"], Token] = "info"
    explanation: str = ""


class Meta(_Model):
    case_type: Annotated[
        Literal["motor_vehicle", "slip_trip_fall", "other", "out_of_scope"], Token
    ] = "other"
    state: str | None = None
    county: str | None = None
    incident_date: date | None = None
    claimant_age: int | None = None
    already_represented: bool | None = None

    @field_validator("state", mode="before")
    @classmethod
    def _normalize_state(cls, v: object) -> str | None:
        if not isinstance(v, str) or not v.strip():
            return None
        token = v.strip()
        code = token.upper()
        if code in STATE_CODES:
            return code
        return STATE_NAMES_TO_CODES.get(token.lower())

    @field_validator("incident_date", mode="before")
    @classmethod
    def _tolerant_date(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return date.fromisoformat(v.strip()[:10])
            except ValueError:
                return None
        return v


class Gates(_Model):
    release_signed: bool | None = None
    fatality_involved: bool | None = None
    workplace_injury: bool | None = None
    government_defendant: bool | None = None
    claimant_status_premises: (
        Annotated[
            Literal[
                "invitee_customer", "licensee_guest", "tenant", "employee", "delivery",
                "trespasser", "unknown",
            ],
            Token,
        ]
        | None
    ) = None


class ObjectiveFinding(_Model):
    status: Annotated[
        Literal["imaging_positive", "imaging_normal", "imaging_pending", "no_imaging",
                "unknown"],
        Token,
    ] = "unknown"
    finding_verbatim: str | None = None
    confidence: Confidence = "absent"


class TreatmentLadder(_Model):
    highest_reached: Annotated[
        Literal[
            "none", "er_only", "conservative_care", "pain_management", "injections",
            "surgery_recommended_written", "surgery_performed",
        ],
        Token,
    ] = "none"
    modalities: list[str] = Field(default_factory=list)
    still_treating: bool | None = None
    future_care_recommended: bool | None = None
    future_care_in_writing: bool | None = None
    impairment_rating_pct: float | None = None

    @field_validator("impairment_rating_pct")
    @classmethod
    def _pct_range(cls, v: float | None) -> float | None:
        if v is None:
            return None
        return min(max(float(v), 0.0), 100.0)


class TreatmentGap(_Model):
    present: bool | None = None
    duration_bucket: (
        Annotated[Literal["none", "30_to_59_days", "60_plus_days", "unknown"], Token] | None
    ) = None
    stated_reason: str | None = None
    reason_mitigating: bool | None = None


class Preexisting(_Model):
    same_body_part_prior_injury: bool | None = None
    treating_within_12mo: bool | None = None
    prior_claims_count: (
        Annotated[Literal["none", "one", "two_plus", "unknown"], Token] | None
    ) = None
    prior_workers_comp: bool | None = None


class Injury(_Model):
    body_parts: list[str] = Field(default_factory=list)
    time_to_first_treatment: (
        Annotated[
            Literal["same_day", "within_72h", "3_to_14_days", "over_14_days", "never",
                    "unknown"],
            Token,
        ]
        | None
    ) = None
    objective_finding: ObjectiveFinding = Field(default_factory=ObjectiveFinding)
    treatment_ladder: TreatmentLadder = Field(default_factory=TreatmentLadder)
    treatment_gap: TreatmentGap = Field(default_factory=TreatmentGap)
    preexisting: Preexisting = Field(default_factory=Preexisting)


class LostWages(_Model):
    claimed: Money = Field(default_factory=Money)
    days_missed: float | None = None
    employment_type: (
        Annotated[
            Literal["w2", "self_employed_1099", "cash_unreported", "unemployed", "retired",
                    "student", "unknown"],
            Token,
        ]
        | None
    ) = None
    verifiable: bool | None = None
    earning_capacity_impaired: bool | None = None


class Liens(_Model):
    payor_type: (
        Annotated[
            Literal[
                "none_self_pay", "private", "medicare", "medicaid", "erisa_selffunded",
                "tricare_va", "medpay_pip", "letter_of_protection", "unknown",
            ],
            Token,
        ]
        | None
    ) = None
    lien_asserted: bool | None = None
    lien_amount: Money = Field(default_factory=Money)
    treating_on_lop: bool | None = None


class Economic(_Model):
    medical_billed_to_date: Money = Field(default_factory=Money)
    future_medical: Money = Field(default_factory=Money)
    out_of_pocket: Money = Field(default_factory=Money)
    lost_wages: LostWages = Field(default_factory=LostWages)
    liens: Liens = Field(default_factory=Liens)


class LiabilityEvidence(_Model):
    police_report: bool | None = None
    citation_issued_to: (
        Annotated[Literal["other_party", "claimant", "both", "neither", "unknown"], Token]
        | None
    ) = None
    admission_of_fault: (
        Annotated[Literal["recorded", "verbal", "none", "unknown"], Token] | None
    ) = None
    independent_witnesses: int | None = None
    photos_of_scene: bool | None = None
    incident_report_same_day: bool | None = None
    surveillance_exists: bool | None = None
    surveillance_preservation_sent: bool | None = None


class Mva(_Model):
    impact_type: (
        Annotated[
            Literal["rear_ended", "t_bone_other_ran_light", "head_on", "sideswipe",
                    "left_turn", "claimant_struck_other", "other"],
            Token,
        ]
        | None
    ) = None
    claimant_role: (
        Annotated[Literal["driver", "passenger", "pedestrian", "cyclist"], Token] | None
    ) = None
    property_damage_level: (
        Annotated[
            Literal["none_visible", "minor_cosmetic", "moderate", "severe", "totaled",
                    "unknown"],
            Token,
        ]
        | None
    ) = None
    vehicle_drivable_after: bool | None = None
    airbags_deployed: bool | None = None
    seatbelt_worn: bool | None = None


class PremisesNotice(_Model):
    theory: Annotated[
        Literal["actual_defendant_created", "actual_prior_complaints",
                "constructive_duration", "none_established"],
        Token,
    ] = "none_established"
    hazard_duration: (
        Annotated[Literal["just_occurred", "minutes", "hours", "days_or_longer", "unknown"],
                  Token]
        | None
    ) = None
    evidentiary_basis: str = ""


class Premises(_Model):
    location_type: str | None = None
    hazard_type: str | None = None
    notice: PremisesNotice | None = None
    warning_present: bool | None = None
    open_and_obvious: (
        Annotated[Literal["hidden", "partially_visible", "plainly_visible", "unknown"], Token]
        | None
    ) = None
    claimant_distraction: str | None = None
    footwear: str | None = None


class Defendant(_Model):
    type: (
        Annotated[
            Literal["individual", "commercial_vehicle", "business_entity", "chain_national",
                    "government", "landlord", "unknown"],
            Token,
        ]
        | None
    ) = None
    acting_in_course_of_employment: bool | None = None
    policy_limits_known: bool | None = None
    policy_limits_amount: Money = Field(default_factory=Money)
    claimant_um_uim: Annotated[Literal["yes", "no", "unsure"], Token] | None = None
    claimant_um_uim_limits: Money = Field(default_factory=Money)


class Liability(_Model):
    self_reported_fault: (
        Annotated[Literal["not_at_all", "slightly", "partly", "mostly", "unsure"], Token]
        | None
    ) = None
    evidence: LiabilityEvidence = Field(default_factory=LiabilityEvidence)
    mva: Mva | None = None
    premises: Premises | None = None
    defendant: Defendant = Field(default_factory=Defendant)


class HumanDamages(_Model):
    activities_lost: list[str] = Field(default_factory=list)
    visible_scarring: bool | None = None
    psychological_impact: bool | None = None
    psychological_treating: bool | None = None
    caregiving_impairment: bool | None = None
    specificity_score: float | None = None

    @field_validator("specificity_score")
    @classmethod
    def _unit_range(cls, v: float | None) -> float | None:
        if v is None:
            return None
        return min(max(float(v), 0.0), 1.0)


class ExtractionNotes(_Model):
    flags: list[ExtractionFlag] = Field(default_factory=list)
    missing_driver_fields: list[str] = Field(default_factory=list)
    internal_inconsistencies: list[str] = Field(default_factory=list)
    model_refusals: list[str] = Field(default_factory=list)


class CanonicalExtraction(_Model):
    meta: Meta = Field(default_factory=Meta)
    gates: Gates = Field(default_factory=Gates)
    injury: Injury = Field(default_factory=Injury)
    economic: Economic = Field(default_factory=Economic)
    liability: Liability = Field(default_factory=Liability)
    human_damages: HumanDamages = Field(default_factory=HumanDamages)
    extraction_notes: ExtractionNotes = Field(default_factory=ExtractionNotes)
