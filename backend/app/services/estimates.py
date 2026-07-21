"""Questionnaire AI advice plus estimate scheduling.

The estimate itself runs as the multi-stage pipeline in
``app.services.estimate_pipeline`` — ``schedule_estimate`` here resets the
row and queues ``run_pipeline`` as a background task.
"""

import json
import logging
import re
from typing import Literal

from fastapi import BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import AppError
from app.models import (
    CaseEstimate,
    EstimateAdvice,
    EstimateStatus,
    InjuryType,
    IntakeSession,
    Question,
    QuestionType,
)
from app.schemas import QuestionIn
from app.services import openrouter
from app.services.email import get_app_settings
from app.services.estimate_pipeline.orchestrator import run_pipeline
from app.services.estimate_pipeline.parsing import extract_json_object as _extract_json_object
from app.services.openrouter import OpenRouterError, ai_configured

logger = logging.getLogger(__name__)

ADVICE_SCHEMA_NAME = "questionnaire_advice"

_QUESTION_TYPE_VALUES = [t.value for t in QuestionType]

_OPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Short patient-facing label"},
        "value": {
            "type": "string",
            "description": "Stable machine value: lowercase letters, digits, underscores",
        },
    },
    "required": ["label", "value"],
    "additionalProperties": False,
}

_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "placeholder": {"type": ["string", "null"]},
        "min": {"type": ["number", "null"]},
        "max": {"type": ["number", "null"]},
        "max_length": {"type": ["integer", "null"]},
        "disallow_future": {"type": ["boolean", "null"]},
    },
    "required": ["placeholder", "min", "max", "max_length", "disallow_future"],
    "additionalProperties": False,
}

_QUESTION_FIELDS = {
    "type": {"type": "string", "enum": _QUESTION_TYPE_VALUES},
    "phase": {
        "type": "string",
        "enum": ["initial", "follow_up"],
        "description": (
            "initial = asked during the deliberately short anonymous onboarding; "
            "follow_up = asked in the portal after signup to refine the estimate"
        ),
    },
    "prompt": {"type": "string"},
    "help_text": {"type": ["string", "null"]},
    "is_required": {"type": "boolean"},
    "config": _CONFIG_SCHEMA,
    "options": {
        "type": "array",
        "items": _OPTION_SCHEMA,
        "description": "2+ entries for single_choice/multi_choice; empty for all other types",
    },
}

ADVICE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {
            "type": "string",
            "description": "Short prose assessment of questionnaire coverage",
        },
        "new_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {**_QUESTION_FIELDS, "rationale": {"type": "string"}},
                "required": [*_QUESTION_FIELDS, "rationale"],
                "additionalProperties": False,
            },
        },
        "question_edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "integer"},
                    "updated": {
                        "type": "object",
                        "properties": _QUESTION_FIELDS,
                        "required": list(_QUESTION_FIELDS),
                        "additionalProperties": False,
                    },
                    "rationale": {"type": "string"},
                    "change_summary": {"type": "string"},
                },
                "required": ["question_id", "updated", "rationale", "change_summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overview", "new_questions", "question_edits"],
    "additionalProperties": False,
}

ADVICE_SYSTEM_PROMPT = (
    "You are a personal-injury intake-design consultant. You will be given the current "
    "intake questionnaire for one injury type as JSON: each question's id, type, prompt, "
    "help text, required flag, options, and config. Determine what information is needed "
    "to accurately estimate (a) the likely settlement payout and (b) the cost of pursuing "
    "the case, and respond with JSON matching the provided schema exactly.\n"
    "- overview: a short prose assessment of what is well covered and what is missing.\n"
    "- new_questions: complete definitions for questions that fill high-impact gaps. "
    "Write prompts in plain, patient-friendly language. Choose the most structured type "
    "that fits (prefer choices over free text). single_choice and multi_choice MUST have "
    "at least 2 options with concise labels and stable values (lowercase letters, digits, "
    "underscores). The us_state_county type is a built-in US state + county picker with "
    "no options — ALWAYS use it (never free text or choices) when the state, county, or "
    "venue of the incident is needed. All other types MUST have an empty options list. "
    "Every question has a phase: set 'initial' ONLY for facts essential to a first rough "
    "estimate — onboarding is deliberately short. Documentation details, insurance "
    "specifics, and refinements are 'follow_up' (asked after the patient signs up). "
    "Only set config keys "
    "that apply to the type (min/max: number; max_length: short_text/long_text; "
    "disallow_future: date; placeholder: text or number types); set every other config "
    "key to null. Never propose a question that duplicates one already in the "
    "questionnaire.\n"
    "- question_edits: propose an edit ONLY when it materially improves estimate "
    "accuracy. 'updated' is the complete replacement definition (all fields, not a "
    "diff) for the question with that exact id. Patients' earlier answers store option "
    "values, so PRESERVE every existing option value exactly and only append new "
    "options or refine labels; never remove or rename option values. change_summary is "
    "one human-readable sentence describing what changed.\n"
    "Propose at most 10 new questions and 5 edits; quality over quantity. General "
    "commentary belongs in overview only."
)

async def schedule_estimate(
    db: AsyncSession, session: IntakeSession, background_tasks: BackgroundTasks
) -> CaseEstimate | None:
    """Create/reset the estimate row and queue the pipeline run. No-op
    (returns None) when AI is unconfigured, so callers fall back to the
    static range."""
    app_settings = await get_app_settings(db)
    if not ai_configured(app_settings):
        return None
    estimate = await db.scalar(
        select(CaseEstimate).where(CaseEstimate.intake_session_id == session.id)
    )
    if estimate is None:
        estimate = CaseEstimate(intake_session_id=session.id)
        db.add(estimate)
    estimate.status = EstimateStatus.pending
    estimate.payout_min = None
    estimate.payout_max = None
    estimate.case_cost_min = None
    estimate.case_cost_max = None
    estimate.gross_min = None
    estimate.gross_max = None
    estimate.net_min = None
    estimate.net_max = None
    estimate.confidence = None
    estimate.reasoning = None
    estimate.missing_info = None
    estimate.result = None
    estimate.internals = None
    estimate.stage_status = None
    estimate.model = None
    estimate.error = None
    await db.commit()
    await db.refresh(estimate)
    background_tasks.add_task(run_pipeline, session.id)
    return estimate


def _advice_messages(
    injury_type: InjuryType,
    questions: list[Question],
    focus_gaps: list[str] | None = None,
) -> list[dict]:
    payload = [
        {
            "id": q.id,
            "type": q.type.value,
            "phase": q.phase,
            "prompt": q.prompt,
            "help_text": q.help_text,
            "is_required": q.is_required,
            "config": q.config or {},
            "options": [{"label": o.label, "value": o.value} for o in q.options],
        }
        for q in questions
    ]
    body = json.dumps(payload, indent=2) if payload else "(no questions yet)"
    content = f"Injury type: {injury_type.name}\n\nCurrent questionnaire (JSON):\n{body}"
    if focus_gaps:
        gap_lines = "\n".join(f"- {gap}" for gap in focus_gaps)
        content += (
            "\n\nA completed intake was analyzed for a settlement estimate, and these "
            f"facts were missing or undocumented:\n{gap_lines}\n"
            "Propose ONLY questions (or edits to existing questions) that would collect "
            "these specific facts. Do not propose unrelated improvements."
        )
    return [
        {"role": "system", "content": ADVICE_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


class RawQuestionProposal(BaseModel):
    """A proposed question as the model emitted it — validated loosely here,
    strictly (via QuestionIn) during sanitization."""

    model_config = ConfigDict(extra="ignore")

    type: QuestionType
    phase: Literal["initial", "follow_up"] = "follow_up"
    prompt: str
    help_text: str | None = None
    is_required: bool = True
    config: dict = Field(default_factory=dict)
    options: list[dict] = Field(default_factory=list)


class RawNewQuestion(RawQuestionProposal):
    rationale: str = ""


class RawQuestionEdit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question_id: int
    updated: RawQuestionProposal
    rationale: str = ""
    change_summary: str = ""


class RawAdvice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    overview: str
    new_questions: list[RawNewQuestion] = Field(default_factory=list)
    question_edits: list[RawQuestionEdit] = Field(default_factory=list)


def parse_advice_content(content: str) -> RawAdvice:
    return RawAdvice.model_validate(_extract_json_object(content))


_CHOICE_TYPES = {QuestionType.single_choice, QuestionType.multi_choice}

# Server-side mirror of the builder's pruneConfig: which config keys each
# question type may carry.
_CONFIG_KEYS_BY_TYPE: dict[QuestionType, set[str]] = {
    QuestionType.short_text: {"placeholder", "max_length"},
    QuestionType.long_text: {"placeholder", "max_length"},
    QuestionType.number: {"placeholder", "min", "max"},
    QuestionType.date: {"disallow_future"},
    QuestionType.single_choice: set(),
    QuestionType.multi_choice: set(),
    QuestionType.yes_no: set(),
    QuestionType.us_state_county: set(),
}

MAX_NEW_PROPOSALS = 15
MAX_EDIT_PROPOSALS = 10


def _slugify_option_value(label: str) -> str:
    """Mirror of the builder's slugifyValue: lowercase, non-alphanumerics to
    underscores, trimmed."""
    return re.sub(r"^_+|_+$", "", re.sub(r"[^a-z0-9]+", "_", label.strip().lower()))


def _sanitize_payload(raw: RawQuestionProposal) -> QuestionIn | None:
    """Normalize one proposed question to a valid QuestionIn, or None if it
    cannot be made valid."""
    config = {
        k: v
        for k, v in (raw.config or {}).items()
        if k in _CONFIG_KEYS_BY_TYPE[raw.type] and v is not None
    }
    options: list[dict] = []
    if raw.type in _CHOICE_TYPES:
        seen_values: set[str] = set()
        for o in raw.options:
            label = str(o.get("label") or "").strip()
            if not label:
                continue
            value = str(o.get("value") or "").strip() or _slugify_option_value(label)
            if not value or value in seen_values:
                continue
            seen_values.add(value)
            options.append({"label": label, "value": value})
        if len(options) < 2:
            return None
    try:
        return QuestionIn.model_validate(
            {
                "type": raw.type,
                "phase": raw.phase,
                "prompt": raw.prompt.strip(),
                "help_text": raw.help_text.strip() if raw.help_text else None,
                "is_required": raw.is_required,
                "config": config,
                "options": options,
            }
        )
    except ValidationError:
        return None


def _edit_is_noop(payload: QuestionIn, question: Question) -> bool:
    return (
        payload.type == question.type
        and payload.prompt == question.prompt
        and payload.help_text == question.help_text
        and payload.is_required == question.is_required
        and payload.config.model_dump(exclude_none=True) == (question.config or {})
        and [(o.label, o.value) for o in payload.options]
        == [(o.label, o.value) for o in question.options]
    )


def sanitize_proposals(raw: RawAdvice, questions: list[Question]) -> list[dict]:
    """Turn the model's raw proposals into validated, deduplicated stored
    proposal dicts with stable ids and applied-state metadata."""
    existing_prompts = {q.prompt.strip().lower() for q in questions}
    questions_by_id = {q.id: q for q in questions}
    proposals: list[dict] = []
    dropped = 0

    seen_add_prompts: set[str] = set()
    add_count = 0
    for item in raw.new_questions:
        payload = _sanitize_payload(item)
        key = item.prompt.strip().lower()
        if (
            payload is None
            or key in existing_prompts
            or key in seen_add_prompts
            or add_count >= MAX_NEW_PROPOSALS
        ):
            dropped += 1
            continue
        seen_add_prompts.add(key)
        add_count += 1
        proposals.append(
            {
                "id": f"add-{add_count}",
                "kind": "add",
                "payload": payload.model_dump(mode="json", exclude_none=True),
                "rationale": item.rationale.strip(),
                "applied": False,
                "applied_at": None,
                "created_question_id": None,
            }
        )

    seen_edit_targets: set[int] = set()
    edit_count = 0
    for edit in raw.question_edits:
        target = questions_by_id.get(edit.question_id)
        payload = _sanitize_payload(edit.updated)
        if (
            target is None
            or payload is None
            or edit.question_id in seen_edit_targets
            or edit_count >= MAX_EDIT_PROPOSALS
            or _edit_is_noop(payload, target)
        ):
            dropped += 1
            continue
        seen_edit_targets.add(edit.question_id)
        edit_count += 1
        proposals.append(
            {
                "id": f"edit-{edit_count}",
                "kind": "edit",
                "question_id": edit.question_id,
                "payload": payload.model_dump(mode="json", exclude_none=True),
                "rationale": edit.rationale.strip(),
                "change_summary": edit.change_summary.strip(),
                "applied": False,
                "applied_at": None,
            }
        )

    if dropped:
        logger.warning("advice sanitization dropped %d invalid/duplicate proposals", dropped)
    return proposals


LOCATION_PROPOSAL = {
    "id": "add-location",
    "kind": "add",
    "payload": {
        "type": "us_state_county",
        "phase": "initial",
        "prompt": "Which state and county did it happen in?",
        "help_text": (
            "Deadlines, fault rules, and typical case values depend on where it happened."
        ),
        "is_required": True,
        "config": {},
        "options": [],
    },
    "rationale": (
        "The estimate flagged the incident state/county as missing — it is one of the "
        "strongest value drivers and gates the legal deadlines, so it is worth asking "
        "up front during onboarding."
    ),
    "applied": False,
    "applied_at": None,
    "created_question_id": None,
}


def ensure_location_proposal(
    advice: EstimateAdvice, questions: list[Question], gaps: list[str]
) -> bool:
    """Guarantee a state+county proposal whenever the estimate flags location
    as missing: the model may fail to propose it, but this gap is too
    important to leave to chance. Returns True if the list changed."""
    mentions_location = any("state" in g.lower() or "county" in g.lower() for g in gaps)
    has_question = any(q.type == QuestionType.us_state_county for q in questions)
    proposals = advice.proposals or []
    has_proposal = any(
        (p.get("payload") or {}).get("type") == QuestionType.us_state_county.value
        for p in proposals
    )
    if not mentions_location or has_question or has_proposal:
        return False
    # Reassignment (not mutation) so SQLAlchemy detects the JSONB change.
    advice.proposals = [dict(LOCATION_PROPOSAL), *proposals]
    return True


async def load_injury_type_questions(db: AsyncSession, injury_type_id: int) -> list[Question]:
    return list(
        await db.scalars(
            select(Question)
            .where(Question.injury_type_id == injury_type_id)
            .order_by(Question.display_order)
            .options(selectinload(Question.options))
        )
    )


async def generate_advice(
    db: AsyncSession, injury_type: InjuryType, focus_gaps: list[str] | None = None
) -> EstimateAdvice:
    """Ask the model what the questionnaire should collect — prose overview plus
    structured question proposals — and upsert the result. With ``focus_gaps``
    (missing facts from a completed estimate) proposals are restricted to
    questions that would collect those facts."""
    app_settings = await get_app_settings(db)
    if not ai_configured(app_settings):
        raise AppError(400, "ai_not_configured", "Configure the OpenRouter key and model first")
    questions = await load_injury_type_questions(db, injury_type.id)
    try:
        content = await openrouter.chat_completion(
            app_settings.openrouter_api_key,
            app_settings.openrouter_model,
            _advice_messages(injury_type, questions, focus_gaps),
            json_schema=ADVICE_JSON_SCHEMA,
            schema_name=ADVICE_SCHEMA_NAME,
            referer=app_settings.app_base_url,
            exclude_reasoning=True,
        )
    except OpenRouterError as exc:
        raise AppError(502, exc.code, exc.message) from exc
    try:
        raw = parse_advice_content(content)
    except (ValueError, ValidationError) as exc:
        logger.warning(
            "advice reply from %s could not be parsed (%s); reply started with: %.2000s",
            app_settings.openrouter_model,
            exc,
            content,
        )
        raise AppError(
            502,
            "ai_invalid_response",
            "The AI reply could not be parsed; try again or switch models",
        ) from exc
    advice = await db.scalar(
        select(EstimateAdvice).where(EstimateAdvice.injury_type_id == injury_type.id)
    )
    if advice is None:
        advice = EstimateAdvice(injury_type_id=injury_type.id, content=raw.overview)
        db.add(advice)
    else:
        advice.content = raw.overview
    advice.proposals = sanitize_proposals(raw, questions)
    advice.model = app_settings.openrouter_model
    await db.commit()
    await db.refresh(advice)
    return advice
