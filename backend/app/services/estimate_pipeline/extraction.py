"""Stage 1 — canonical extraction (temperature 0, strict schema).

Maps whatever questionnaire an admin built into the fixed canonical schema.
Unasked facts become nulls, which widen the published range downstream.
Extraction failure fails the whole pipeline run: every later stage consumes
this output.
"""

from pydantic import ValidationError

from app.services import openrouter
from app.services.estimate_pipeline.canonical import (
    EXTRACTION_JSON_SCHEMA,
    EXTRACTION_SCHEMA_NAME,
    CanonicalExtraction,
)
from app.services.estimate_pipeline.parsing import call_with_schema_repair, extract_json_object

# Sized for always-on reasoning models (Kimi K3 etc.), which can take minutes.
EXTRACTION_TIMEOUT = 180.0

EXTRACTION_SYSTEM_PROMPT = (
    "You are a data-extraction engine for a personal-injury intake platform. You are "
    "given one claimant's questionnaire answers as `- [slug] question: answer` lines. "
    "Map them into the provided JSON schema. Rules:\n"
    "- Extract FACTS only. Do not estimate case value, damages, fault percentages, or "
    "severity. Do not output dollar figures beyond amounts the claimant reported.\n"
    "- NEVER infer a value that was not stated. Use null for anything not answered or "
    "not derivable from an explicit answer. '(not answered)' means null.\n"
    "- Set `documented` true ONLY where the claimant affirmatively indicated a document "
    "exists (bill, billing statement, pay stub, written recommendation). Silence means "
    "false.\n"
    "- Set per-field `confidence`: high for explicit answers, medium for clear but "
    "qualitative ones, low for vague or hedged ones, absent when unanswered.\n"
    "- `source_field` is the [slug] the value came from.\n"
    "- Populate `mva` only for motor-vehicle incidents and `premises` only for "
    "slip/trip/fall incidents; set the other to null.\n"
    "- Record contradictions between answers in extraction_notes.internal_inconsistencies "
    "and list unanswered high-signal facts in extraction_notes.missing_driver_fields.\n"
    "- List every field you left null for lack of basis in extraction_notes."
    "model_refusals. On a sparsely answered questionnaire this list must not be empty.\n"
    "Respond with JSON only, matching the schema exactly."
)


def build_extraction_messages(
    injury_type_name: str, qa_pairs: list[tuple[str, str, str]]
) -> list[dict]:
    """qa_pairs: (slug, prompt, display_answer) triples."""
    lines = "\n".join(f"- [{slug}] {prompt}: {answer}" for slug, prompt, answer in qa_pairs)
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Injury type: {injury_type_name}\n\nQuestionnaire answers:\n{lines}",
        },
    ]


def parse_extraction(content: str) -> CanonicalExtraction:
    """Raises ValueError/ValidationError on an unusable reply."""
    return CanonicalExtraction.model_validate(extract_json_object(content))


async def run_extraction(
    api_key: str,
    model: str,
    injury_type_name: str,
    qa_pairs: list[tuple[str, str, str]],
    referer: str | None = None,
) -> CanonicalExtraction:
    """One temperature-0 structured call. Raises OpenRouterError, ValueError,
    or ValidationError — the orchestrator fails the run on any of them."""
    async def _call(messages: list[dict]) -> str:
        return await openrouter.chat_completion(
            api_key,
            model,
            messages,
            json_schema=EXTRACTION_JSON_SCHEMA,
            schema_name=EXTRACTION_SCHEMA_NAME,
            referer=referer,
            temperature=0.0,
            timeout=EXTRACTION_TIMEOUT,
            exclude_reasoning=True,
        )

    return await call_with_schema_repair(
        _call, build_extraction_messages(injury_type_name, qa_pairs), parse_extraction
    )


__all__ = [
    "EXTRACTION_SYSTEM_PROMPT",
    "build_extraction_messages",
    "parse_extraction",
    "run_extraction",
    "ValidationError",
]
