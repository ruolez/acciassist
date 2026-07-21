"""Stage 3 — comparable verdicts/settlements via a search-enabled model.

Optional (admin toggle) and fully degradable: any failure here is recorded
and the pipeline continues without a comps anchor. Results are code-side
sanitized and weighted by source quality — firm-marketing pages are an
upward-biased sample (they publish wins), so published verdicts count most.
"""

from pydantic import BaseModel, ConfigDict, field_validator

from app.services import openrouter
from app.services.estimate_pipeline.assembly import COMPS_MAX_AMOUNT, CompsSummary
from app.services.estimate_pipeline.canonical import CanonicalExtraction
from app.services.estimate_pipeline.parsing import extract_json_object

COMPS_SCHEMA_NAME = "comparable_results"
# Sized for always-on reasoning models (Kimi K3 etc.) plus web-search latency.
COMPS_TIMEOUT = 180.0

COMPS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "comps": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "injury_match": {"type": "string"},
                    "venue": {"type": "string"},
                    "amount": {"type": "number"},
                    "year": {"type": ["integer", "null"]},
                    "kind": {"type": "string", "enum": ["verdict", "settlement", "unknown"]},
                    "source_url": {"type": ["string", "null"]},
                    "source_quality": {
                        "type": "string",
                        "enum": ["published_verdict", "news", "firm_marketing"],
                    },
                },
                "required": [
                    "description",
                    "injury_match",
                    "venue",
                    "amount",
                    "year",
                    "kind",
                    "source_url",
                    "source_quality",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["comps"],
    "additionalProperties": False,
}

COMPS_SYSTEM_PROMPT = (
    "You are a legal researcher with web search. Find 5-10 reported verdicts or "
    "settlements comparable to the case described: match the injury and treatment "
    "level, the venue (county first, then state), the liability posture, and prefer "
    "results from the last five years. Return ONLY results you can cite to a URL. If "
    "you cannot find five, return what you found — do not extrapolate or invent. "
    "Classify each source honestly: published_verdict for verdict reporters, court "
    "opinions, or bar-journal roundups; news for journalism; firm_marketing for law-firm "
    "results pages (these advertise wins and skew high). Respond with JSON matching "
    "the schema."
)


class CompEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = ""
    injury_match: str = ""
    venue: str = ""
    amount: float
    year: int | None = None
    kind: str = "unknown"
    source_url: str | None = None
    source_quality: str = "firm_marketing"

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        return v if v in ("verdict", "settlement") else "unknown"

    @field_validator("source_quality")
    @classmethod
    def _quality(cls, v: str) -> str:
        return v if v in ("published_verdict", "news") else "firm_marketing"


class CompsReply(BaseModel):
    model_config = ConfigDict(extra="ignore")

    comps: list[CompEntry] = []


def build_comps_messages(x: CanonicalExtraction, injury_type_name: str) -> list[dict]:
    ladder = x.injury.treatment_ladder.highest_reached
    finding = x.injury.objective_finding.finding_verbatim or x.injury.objective_finding.status
    venue = ", ".join(p for p in (x.meta.county, x.meta.state) if p) or "unknown venue"
    liability = "unknown"
    if x.liability.mva is not None and x.liability.mva.impact_type:
        liability = x.liability.mva.impact_type.replace("_", " ")
    elif x.liability.premises is not None and x.liability.premises.hazard_type:
        liability = f"premises: {x.liability.premises.hazard_type}"
    query = (
        f"Case type: {injury_type_name}\n"
        f"Injury: {', '.join(x.injury.body_parts) or 'unspecified'} — {finding}; "
        f"treatment level: {ladder}\n"
        f"Venue: {venue} (expand to the state if fewer than 3 county matches)\n"
        f"Liability posture: {liability}"
    )
    return [
        {"role": "system", "content": COMPS_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]


def _annotation_urls(annotations: list) -> list[str]:
    urls = []
    for a in annotations or []:
        url = (a.get("url_citation") or {}).get("url") if isinstance(a, dict) else None
        if url:
            urls.append(url)
    return urls


def parse_comps(content: str, annotations: list) -> CompsSummary:
    reply = CompsReply.model_validate(extract_json_object(content))
    urls = _annotation_urls(annotations)
    entries = []
    for entry in reply.comps:
        if not (0 < entry.amount <= COMPS_MAX_AMOUNT):
            continue
        if entry.source_url is None and urls:
            entry.source_url = urls.pop(0)
        entries.append(entry.model_dump(mode="json"))
    return CompsSummary(comps=entries)


def resolve_comps_model(comps_model: str | None, main_model: str) -> str:
    """An explicit comps model is used verbatim (it may already be a search
    model); otherwise the main model gets OpenRouter's web-plugin suffix."""
    if comps_model:
        return comps_model
    return main_model if main_model.endswith(":online") else f"{main_model}:online"


async def run_comps(
    api_key: str,
    model: str,
    x: CanonicalExtraction,
    injury_type_name: str,
    referer: str | None = None,
) -> CompsSummary:
    content, annotations = await openrouter.chat_completion(
        api_key,
        model,
        build_comps_messages(x, injury_type_name),
        json_schema=COMPS_JSON_SCHEMA,
        schema_name=COMPS_SCHEMA_NAME,
        referer=referer,
        timeout=COMPS_TIMEOUT,
        # Web routing plus require_parameters often matches no provider; the
        # schema is still requested but routing stays permissive.
        require_parameters=False,
        return_annotations=True,
        exclude_reasoning=True,
    )
    return parse_comps(content, annotations)
