"""Stage 5 — adversarial pass: the defense adjuster's lowest defensible offer.

The floor anchor is expressed as a PERCENT of weighted specials, never a
dollar figure, so valuation stays in code. The attack arguments become the
patient-facing "what could reduce your estimate" section. This stage is
degradable: on failure the pipeline continues without a floor anchor.
"""

import json

from pydantic import BaseModel, ConfigDict, field_validator

from app.services import openrouter
from app.services.estimate_pipeline.assembly import AdversarialSummary
from app.services.estimate_pipeline.canonical import CanonicalExtraction
from app.services.estimate_pipeline.parsing import call_with_schema_repair, extract_json_object

ADVERSARIAL_SCHEMA_NAME = "adjuster_review"
ADVERSARIAL_TEMPERATURE = 0.3
# Sized for always-on reasoning models (Kimi K3 etc.), which can take minutes.
ADVERSARIAL_HTTP_TIMEOUT = 180.0

_ATTACK_CATEGORIES = [
    "causation",
    "treatment_gap",
    "pre_existing",
    "comparative_fault",
    "documentation",
    "over_treatment",
    "credibility",
]

ADVERSARIAL_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "lowest_defensible_pct_of_specials": {
            "type": "number",
            "minimum": 0,
            "maximum": 300,
            "description": (
                "The lowest offer you could defend, expressed as a percent of the "
                "claimant's provable special damages (100 = specials with nothing for "
                "pain and suffering). Do NOT output dollars."
            ),
        },
        "low_rationale": {"type": "string"},
        "attack_arguments": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": _ATTACK_CATEGORIES},
                    "argument": {
                        "type": "string",
                        "description": "One plain-language sentence a claimant can understand.",
                    },
                },
                "required": ["category", "argument"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lowest_defensible_pct_of_specials", "low_rationale", "attack_arguments"],
    "additionalProperties": False,
}

ADVERSARIAL_SYSTEM_PROMPT = (
    "You are a claims adjuster for the defendant's insurance carrier. You are given a "
    "structured extraction of the claimant's intake answers. Your job is to justify "
    "the LOWEST defensible settlement offer. Attack: causation, delayed or gapped "
    "treatment, pre-existing conditions, the claimant's comparative fault, "
    "credibility, over-treatment, and whether the claimed damages are actually "
    "documented. Respond with JSON matching the schema: the lowest offer you could "
    "defend as a PERCENT of provable special damages (never dollars), and the three "
    "arguments you would lead with, phrased so a claimant can understand what would "
    "be used against them."
)


class AdversarialReply(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lowest_defensible_pct_of_specials: float
    low_rationale: str = ""
    attack_arguments: list[dict] = []

    @field_validator("lowest_defensible_pct_of_specials")
    @classmethod
    def _pct_range(cls, v: float) -> float:
        return min(max(float(v), 0.0), 300.0)

    @field_validator("attack_arguments")
    @classmethod
    def _clean_arguments(cls, v: list) -> list[dict]:
        cleaned = []
        for item in v[:3]:
            if isinstance(item, dict) and str(item.get("argument") or "").strip():
                cleaned.append(
                    {
                        "category": str(item.get("category") or "other"),
                        "argument": str(item["argument"]).strip(),
                    }
                )
        return cleaned


def build_adversarial_messages(x: CanonicalExtraction, rule_summary: str | None) -> list[dict]:
    body = json.dumps(x.model_dump(mode="json"), indent=2)
    jurisdiction = f"\n\nJurisdiction: {rule_summary}" if rule_summary else ""
    return [
        {"role": "system", "content": ADVERSARIAL_SYSTEM_PROMPT},
        {"role": "user", "content": f"Case extraction:\n{body}{jurisdiction}"},
    ]


def parse_adversarial(content: str) -> AdversarialSummary:
    reply = AdversarialReply.model_validate(extract_json_object(content))
    return AdversarialSummary(
        lowest_defensible_pct_of_specials=reply.lowest_defensible_pct_of_specials,
        low_rationale=reply.low_rationale,
        attack_arguments=reply.attack_arguments,
    )


def describe_rule(rule) -> str | None:
    if rule is None:
        return None
    parts = [f"{rule.state_name}: {rule.comparative_rule} comparative negligence"]
    if rule.no_fault:
        parts.append("no-fault/PIP state")
    return "; ".join(parts)


async def run_adversarial(
    api_key: str,
    model: str,
    x: CanonicalExtraction,
    rule,
    referer: str | None = None,
) -> AdversarialSummary:
    async def _call(messages: list[dict]) -> str:
        return await openrouter.chat_completion(
            api_key,
            model,
            messages,
            json_schema=ADVERSARIAL_JSON_SCHEMA,
            schema_name=ADVERSARIAL_SCHEMA_NAME,
            referer=referer,
            temperature=ADVERSARIAL_TEMPERATURE,
            timeout=ADVERSARIAL_HTTP_TIMEOUT,
            exclude_reasoning=True,
        )

    return await call_with_schema_repair(
        _call, build_adversarial_messages(x, describe_rule(rule)), parse_adversarial
    )
