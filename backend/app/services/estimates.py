"""AI case estimation and questionnaire advice via OpenRouter.

run_estimate is a fire-and-forget background task (mirrors notifications.py:
it opens its own session because the request session is closed by the time it
runs, and it never raises — failures land in case_estimates.error).
"""

import json
import logging
import re
import uuid
from typing import Literal

from fastapi import BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import AppError
from app.models import (
    CaseEstimate,
    EstimateAdvice,
    EstimateStatus,
    InjuryType,
    IntakeAnswer,
    IntakeSession,
    Question,
    QuestionType,
)
from app.schemas import QuestionIn
from app.services import email as email_service
from app.services import openrouter
from app.services.email import get_app_settings
from app.services.estimate_pipeline.parsing import extract_json_object as _extract_json_object
from app.services.openrouter import OpenRouterError, ai_configured
from app.services.summary import answer_display_value

logger = logging.getLogger(__name__)

ESTIMATE_SCHEMA_NAME = "case_estimate"
ESTIMATE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "payout_min": {
            "type": "integer",
            "description": "Low end of the estimated settlement payout in whole US dollars",
        },
        "payout_max": {
            "type": "integer",
            "description": "High end of the estimated settlement payout in whole US dollars",
        },
        "case_cost_min": {
            "type": "integer",
            "description": "Low end of the estimated cost to pursue the case in whole US dollars",
        },
        "case_cost_max": {
            "type": "integer",
            "description": "High end of the estimated cost to pursue the case in whole US dollars",
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of the estimate, 2-4 sentences",
        },
        "missing_information": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Facts not collected in the answers that would most improve accuracy",
        },
    },
    "required": [
        "payout_min",
        "payout_max",
        "case_cost_min",
        "case_cost_max",
        "confidence",
        "reasoning",
        "missing_information",
    ],
    "additionalProperties": False,
}

ESTIMATE_SYSTEM_PROMPT = (
    "You are a personal-injury case evaluator for a US claims-assistance firm. "
    "You are given the injury type and a patient's intake questionnaire answers. "
    "Estimate a realistic settlement payout range and the firm's likely cost range to "
    "pursue the case (medical record retrieval, expert review, filing, negotiation "
    "overhead), both in whole US dollars. Be conservative: wide ranges and \"low\" "
    "confidence are correct when key facts (medical treatment, liability, insurance "
    "status) are missing. Do not inflate figures. If the answers describe no "
    "compensable injury, return 0 for both payout bounds with low confidence and "
    "explain why in reasoning. Respond with JSON only, matching the provided schema "
    "exactly: integer USD amounts, payout_min <= payout_max, "
    "case_cost_min <= case_cost_max."
)

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
    "underscores). All other types MUST have an empty options list. Only set config keys "
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

class EstimateResult(BaseModel):
    payout_min: int
    payout_max: int
    case_cost_min: int
    case_cost_max: int
    confidence: Literal["low", "medium", "high"]
    reasoning: str
    missing_information: list[str]

    @model_validator(mode="after")
    def _sane_ranges(self) -> "EstimateResult":
        self.payout_min = max(self.payout_min, 0)
        self.payout_max = max(self.payout_max, 0)
        self.case_cost_min = max(self.case_cost_min, 0)
        self.case_cost_max = max(self.case_cost_max, 0)
        if self.payout_min > self.payout_max:
            self.payout_min, self.payout_max = self.payout_max, self.payout_min
        if self.case_cost_min > self.case_cost_max:
            self.case_cost_min, self.case_cost_max = self.case_cost_max, self.case_cost_min
        return self


def parse_estimate_content(content: str) -> EstimateResult:
    return EstimateResult.model_validate(_extract_json_object(content))


async def build_qa_pairs(db: AsyncSession, session: IntakeSession) -> list[tuple[str, str]]:
    """Human-readable (question prompt, answer) pairs for the AI prompt."""
    questions = await db.scalars(
        select(Question)
        .where(Question.injury_type_id == session.injury_type_id)
        .order_by(Question.display_order)
        .options(selectinload(Question.options))
    )
    answers = {
        a.question_id: a.value
        for a in await db.scalars(
            select(IntakeAnswer).where(IntakeAnswer.session_id == session.id)
        )
    }
    pairs = []
    for q in questions:
        labels = {o.value: o.label for o in q.options}
        if q.id in answers:
            display = answer_display_value(q.type, answers[q.id], labels)
        else:
            display = "(not answered)"
        pairs.append((q.prompt, display or "(not answered)"))
    return pairs


def _estimate_messages(injury_type_name: str, pairs: list[tuple[str, str]]) -> list[dict]:
    lines = "\n".join(f"- {prompt}: {answer}" for prompt, answer in pairs)
    return [
        {"role": "system", "content": ESTIMATE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Injury type: {injury_type_name}\n\nQuestionnaire answers:\n{lines}",
        },
    ]


async def run_estimate(session_id: uuid.UUID) -> None:
    """Background task: call the model and record the outcome. Never raises."""
    factory = email_service.get_session_factory()
    async with factory() as db:
        estimate = await db.scalar(
            select(CaseEstimate).where(CaseEstimate.intake_session_id == session_id)
        )
        if estimate is None:
            logger.warning("run_estimate: no estimate row for session %s", session_id)
            return
        try:
            session = await db.get(IntakeSession, session_id)
            app_settings = await get_app_settings(db)
            if session is None or not ai_configured(app_settings):
                raise OpenRouterError("ai_not_configured", "AI is not configured")
            injury_type_name = await db.scalar(
                select(InjuryType.name).where(InjuryType.id == session.injury_type_id)
            )
            pairs = await build_qa_pairs(db, session)
            content = await openrouter.chat_completion(
                app_settings.openrouter_api_key,
                app_settings.openrouter_model,
                _estimate_messages(injury_type_name or "Unknown", pairs),
                json_schema=ESTIMATE_JSON_SCHEMA,
                schema_name=ESTIMATE_SCHEMA_NAME,
                referer=app_settings.app_base_url,
            )
            result = parse_estimate_content(content)
        except (OpenRouterError, ValueError, ValidationError) as exc:
            logger.warning("estimate for session %s failed: %s", session_id, exc)
            estimate.status = EstimateStatus.failed
            estimate.error = str(exc)[:2000]
            await db.commit()
            return
        estimate.status = EstimateStatus.completed
        estimate.payout_min = result.payout_min
        estimate.payout_max = result.payout_max
        estimate.case_cost_min = result.case_cost_min
        estimate.case_cost_max = result.case_cost_max
        estimate.confidence = result.confidence
        estimate.reasoning = result.reasoning
        estimate.missing_info = result.missing_information
        estimate.model = app_settings.openrouter_model
        estimate.error = None
        await db.commit()


async def schedule_estimate(
    db: AsyncSession, session: IntakeSession, background_tasks: BackgroundTasks
) -> CaseEstimate | None:
    """Create/reset the estimate row and queue the model call. No-op (returns
    None) when AI is unconfigured, so callers fall back to the static range."""
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
    estimate.confidence = None
    estimate.reasoning = None
    estimate.missing_info = None
    estimate.model = None
    estimate.error = None
    await db.commit()
    await db.refresh(estimate)
    background_tasks.add_task(run_estimate, session.id)
    return estimate


def _advice_messages(injury_type: InjuryType, questions: list[Question]) -> list[dict]:
    payload = [
        {
            "id": q.id,
            "type": q.type.value,
            "prompt": q.prompt,
            "help_text": q.help_text,
            "is_required": q.is_required,
            "config": q.config or {},
            "options": [{"label": o.label, "value": o.value} for o in q.options],
        }
        for q in questions
    ]
    body = json.dumps(payload, indent=2) if payload else "(no questions yet)"
    return [
        {"role": "system", "content": ADVICE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Injury type: {injury_type.name}\n\nCurrent questionnaire (JSON):\n{body}"
            ),
        },
    ]


class RawQuestionProposal(BaseModel):
    """A proposed question as the model emitted it — validated loosely here,
    strictly (via QuestionIn) during sanitization."""

    model_config = ConfigDict(extra="ignore")

    type: QuestionType
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


async def load_injury_type_questions(db: AsyncSession, injury_type_id: int) -> list[Question]:
    return list(
        await db.scalars(
            select(Question)
            .where(Question.injury_type_id == injury_type_id)
            .order_by(Question.display_order)
            .options(selectinload(Question.options))
        )
    )


async def generate_advice(db: AsyncSession, injury_type: InjuryType) -> EstimateAdvice:
    """Ask the model what the questionnaire should collect — prose overview plus
    structured question proposals — and upsert the result."""
    app_settings = await get_app_settings(db)
    if not ai_configured(app_settings):
        raise AppError(400, "ai_not_configured", "Configure the OpenRouter key and model first")
    questions = await load_injury_type_questions(db, injury_type.id)
    try:
        content = await openrouter.chat_completion(
            app_settings.openrouter_api_key,
            app_settings.openrouter_model,
            _advice_messages(injury_type, questions),
            json_schema=ADVICE_JSON_SCHEMA,
            schema_name=ADVICE_SCHEMA_NAME,
            referer=app_settings.app_base_url,
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
