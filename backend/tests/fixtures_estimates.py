"""Shared fixtures for pipeline tests: canned per-stage model replies and a
chat_completion dispatcher keyed on schema_name."""

import json

# A documented, clear-liability rear-end MVA in California.
EXTRACTION_REAR_END_CA = {
    "meta": {"case_type": "motor_vehicle", "state": "CA", "county": "San Bernardino",
             "incident_date": "2026-01-15"},
    "gates": {},
    "injury": {
        "body_parts": ["neck"],
        "objective_finding": {"status": "imaging_positive",
                              "finding_verbatim": "C5-C6 herniation", "confidence": "high"},
        "treatment_ladder": {"highest_reached": "injections"},
    },
    "economic": {
        "medical_billed_to_date": {"amount": 18400, "documented": True,
                                   "confidence": "high", "source_field": "medical_bills_amount"},
        "liens": {"payor_type": "private"},
    },
    "liability": {
        "evidence": {"citation_issued_to": "other_party", "police_report": True},
        "mva": {"impact_type": "rear_ended", "property_damage_level": "severe"},
    },
    "extraction_notes": {"model_refusals": ["claimant_age"]},
}

# Sparse soft-tissue claim, state unknown.
EXTRACTION_SPARSE = {
    "meta": {"case_type": "motor_vehicle"},
    "injury": {"objective_finding": {"status": "no_imaging"}},
    "economic": {"medical_billed_to_date": {"amount": 3000, "documented": False}},
    "extraction_notes": {
        "missing_driver_fields": ["state", "impact_type", "police_report"],
        "model_refusals": ["state", "county", "incident_date"],
    },
}

# SOL-expired case in Tennessee (1-year SOL).
EXTRACTION_SOL_EXPIRED = {
    "meta": {"case_type": "motor_vehicle", "state": "TN", "incident_date": "2020-01-01"},
    "injury": {"objective_finding": {"status": "imaging_positive"}},
    "economic": {"medical_billed_to_date": {"amount": 30000, "documented": True}},
}

# Premises fall by a trespasser.
EXTRACTION_TRESPASSER = {
    "meta": {"case_type": "slip_trip_fall", "state": "CA", "incident_date": "2026-05-01"},
    "gates": {"claimant_status_premises": "trespasser"},
    "liability": {"premises": {"hazard_type": "broken stair",
                               "notice": {"theory": "none_established",
                                          "evidentiary_basis": "none"}}},
}

# Soft-tissue MVA in no-fault New York — below the serious-injury threshold.
EXTRACTION_NO_FAULT_SOFT = {
    "meta": {"case_type": "motor_vehicle", "state": "NY", "incident_date": "2026-05-01"},
    "injury": {"objective_finding": {"status": "no_imaging"},
               "treatment_ladder": {"highest_reached": "conservative_care"}},
    "economic": {"medical_billed_to_date": {"amount": 4000, "documented": True}},
}

JUDGMENT_REPLY = {
    "severity_tier": 3,
    "tier_rationale": "Objective imaging finding with injections, no surgery.",
    "swing_fact": "A written surgery recommendation would move this to tier 4.",
    "defendant_liability_pct": 90,
    "liability_rationale": "Rear-end impact with a citation to the other driver.",
}

ADVERSARIAL_REPLY = {
    "lowest_defensible_pct_of_specials": 70,
    "low_rationale": "Gap risk and pre-existing questions justify a specials-level offer.",
    "attack_arguments": [
        {"category": "causation", "argument": "The defense will question delayed treatment."},
        {"category": "documentation", "argument": "Future care costs are not in writing."},
    ],
}

COMPS_REPLY = {
    "comps": [
        {"description": "Cervical herniation, injections", "injury_match": "close",
         "venue": "San Bernardino County, CA", "amount": 95000, "year": 2024,
         "kind": "settlement", "source_url": "https://example.com/verdict1",
         "source_quality": "published_verdict"},
        {"description": "Neck injury rear-end", "injury_match": "close",
         "venue": "CA", "amount": 120000, "year": 2023, "kind": "verdict",
         "source_url": None, "source_quality": "firm_marketing"},
    ]
}

COMPS_ANNOTATIONS = [
    {"type": "url_citation", "url_citation": {"url": "https://example.com/cited"}}
]


class PipelineDispatcher:
    """Fake openrouter.chat_completion keyed on schema_name. Tests mutate
    `replies` / `errors` to shape a scenario and inspect `calls` after."""

    def __init__(self, extraction: dict = EXTRACTION_REAR_END_CA):
        self.replies: dict[str, dict] = {
            "case_extraction": extraction,
            "case_judgment": JUDGMENT_REPLY,
            "adjuster_review": ADVERSARIAL_REPLY,
            "comparable_results": COMPS_REPLY,
        }
        # schema_name -> exception to raise (or a callable(call_index)->reply|raise)
        self.errors: dict[str, Exception] = {}
        self.judgment_hook = None  # optional callable(nth_judgment_call) -> dict | Exception
        self.calls: list[dict] = []

    async def __call__(self, api_key, model, messages, json_schema=None,
                       schema_name="response", referer=None, temperature=None,
                       plugins=None, timeout=60.0, require_parameters=True,
                       return_annotations=False):
        record = {
            "model": model, "schema_name": schema_name, "temperature": temperature,
            "messages": messages, "json_schema": json_schema,
            "require_parameters": require_parameters,
        }
        self.calls.append(record)
        if schema_name in self.errors:
            raise self.errors[schema_name]
        if schema_name == "case_judgment" and self.judgment_hook is not None:
            nth = sum(1 for c in self.calls if c["schema_name"] == "case_judgment") - 1
            outcome = self.judgment_hook(nth)
            if isinstance(outcome, Exception):
                raise outcome
            return json.dumps(outcome)
        reply = json.dumps(self.replies[schema_name])
        if return_annotations:
            return reply, COMPS_ANNOTATIONS
        return reply


async def seed_ai_settings(session_factory, **overrides) -> None:
    from app.services.email import get_app_settings

    async with session_factory() as s:
        row = await get_app_settings(s)
        row.openrouter_api_key = "sk-or-test"
        row.openrouter_model = "test/model"
        for key, value in overrides.items():
            setattr(row, key, value)
        await s.commit()


async def seed_jurisdictions(session_factory) -> None:
    from app.services.estimate_pipeline.jurisdiction_data import seed_jurisdiction_defaults

    async with session_factory() as s:
        await seed_jurisdiction_defaults(s)
        await s.commit()


async def completed_session(admin_client) -> str:
    """Publish a minimal questionnaire, answer it, and complete the intake."""
    resp = await admin_client.post(
        "/api/admin/injury-types", json={"name": "Auto Accident", "is_published": True}
    )
    itid = resp.json()["id"]
    q = (
        await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "yes_no", "prompt": "Were you injured?"},
        )
    ).json()
    sid = (
        await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
    ).json()["session_id"]
    await admin_client.post(
        f"/api/intake/{sid}/answers",
        json={"answers": [{"question_id": q["id"], "value": True}]},
    )
    resp = await admin_client.post(f"/api/intake/{sid}/complete")
    assert resp.status_code == 200
    return sid
