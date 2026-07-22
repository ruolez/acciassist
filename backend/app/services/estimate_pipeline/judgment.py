"""Stage 4 — sampled judgment (severity tier + liability percent).

The genuinely subjective calls are sampled N times at temperature 0.7; code
takes the median and uses the spread as an honest uncertainty signal for the
published range width. The model is given an anchored rubric and is
explicitly forbidden from outputting dollar amounts.
"""

import json
import math
from statistics import median

from pydantic import BaseModel, ConfigDict, field_validator

from app.services import openrouter
from app.services.estimate_pipeline.assembly import JudgmentAggregate
from app.services.estimate_pipeline.canonical import CanonicalExtraction
from app.services.estimate_pipeline.parsing import extract_json_object

JUDGMENT_SCHEMA_NAME = "case_judgment"
JUDGMENT_TEMPERATURE = 0.7
# Sized for always-on reasoning models (Kimi K3 etc.), which can take minutes.
JUDGMENT_TIMEOUT = 180.0

JUDGMENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "severity_tier": {"type": "integer", "minimum": 1, "maximum": 5},
        "tier_rationale": {"type": "string"},
        "swing_fact": {
            "type": "string",
            "description": (
                "The single fact that most nearly moved this case to the adjacent "
                "tier — expose your margin."
            ),
        },
        "defendant_liability_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "liability_rationale": {"type": "string"},
    },
    "required": [
        "severity_tier",
        "tier_rationale",
        "swing_fact",
        "defendant_liability_pct",
        "liability_rationale",
    ],
    "additionalProperties": False,
}

JUDGMENT_SYSTEM_PROMPT = (
    "You are a personal-injury case evaluator. You are given a structured extraction "
    "of one claimant's intake answers. Make exactly two judgments and respond with "
    "JSON matching the schema. NEVER output a dollar amount or a settlement value — "
    "valuation happens elsewhere.\n\n"
    "1. severity_tier — assign using ONLY these anchors:\n"
    "   1 — Soft tissue, no imaging findings, under 8 weeks of conservative care\n"
    "   2 — Soft tissue with 3-6 months of treatment, or a minor fracture that healed\n"
    "   3 — Objective imaging finding, injections, no surgery\n"
    "   4 — Surgery performed, or formally recommended in writing\n"
    "   5 — Permanent impairment, disability rating, or catastrophic injury\n"
    "   Then state in swing_fact the ONE fact that most nearly moved this to an "
    "adjacent tier.\n\n"
    "2. defendant_liability_pct — the percentage of fault a jury would likely assign "
    "to the defendant(s), 0-100, from the liability facts only (impact type, "
    "citations, admissions, witnesses, notice evidence, claimant distraction). Judge "
    "the facts; do not simply repeat the claimant's self-assessment.\n\n"
    "Base both judgments strictly on stated facts. Unverified or undocumented claims "
    "deserve skepticism, not charity."
)


class JudgmentSample(BaseModel):
    model_config = ConfigDict(extra="ignore")

    severity_tier: int
    tier_rationale: str = ""
    swing_fact: str = ""
    defendant_liability_pct: float
    liability_rationale: str = ""

    @field_validator("severity_tier")
    @classmethod
    def _tier_range(cls, v: int) -> int:
        return min(max(int(v), 1), 5)

    @field_validator("defendant_liability_pct")
    @classmethod
    def _pct_range(cls, v: float) -> float:
        return min(max(float(v), 0.0), 100.0)


def build_judgment_messages(x: CanonicalExtraction) -> list[dict]:
    body = json.dumps(x.model_dump(mode="json"), indent=2)
    return [
        {"role": "system", "content": JUDGMENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Case extraction:\n{body}"},
    ]


def parse_judgment(content: str) -> JudgmentSample:
    return JudgmentSample.model_validate(extract_json_object(content))


async def sample_once(
    api_key: str, model: str, x: CanonicalExtraction, referer: str | None = None
) -> JudgmentSample:
    content = await openrouter.chat_completion(
        api_key,
        model,
        build_judgment_messages(x),
        json_schema=JUDGMENT_JSON_SCHEMA,
        schema_name=JUDGMENT_SCHEMA_NAME,
        referer=referer,
        temperature=JUDGMENT_TEMPERATURE,
        timeout=JUDGMENT_TIMEOUT,
    )
    return parse_judgment(content)


def minimum_valid_samples(requested: int) -> int:
    return math.ceil(requested / 2)


def aggregate_samples(samples: list[JudgmentSample]) -> JudgmentAggregate:
    if not samples:
        raise ValueError("no judgment samples to aggregate")
    tiers = [s.severity_tier for s in samples]
    pcts = [s.defendant_liability_pct for s in samples]
    return JudgmentAggregate(
        median_tier=math.floor(median(tiers) + 0.5),
        median_liability_pct=float(median(pcts)),
        tier_spread=max(tiers) - min(tiers),
        liability_spread=max(pcts) - min(pcts),
        swing_facts=[s.swing_fact for s in samples if s.swing_fact],
    )
