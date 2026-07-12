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
from pydantic import BaseModel, ValidationError, model_validator
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
)
from app.services import email as email_service
from app.services import openrouter
from app.services.email import get_app_settings
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

ADVICE_SYSTEM_PROMPT = (
    "You are a personal-injury intake-design consultant. You will be given the "
    "current intake questionnaire for one injury type: each question's prompt, "
    "answer type, required flag, and answer options where applicable. Your job: "
    "identify what information is needed to accurately estimate (a) the likely "
    "settlement payout and (b) the cost of pursuing the case, and compare that "
    "against what the questionnaire already collects. Respond in plain text with "
    'three short sections: "Well covered" (what current questions already capture), '
    '"Missing — high impact" (specific questions to add, each with a suggested '
    'answer type and options), and "Suggested refinements" (changes to existing '
    "questions). Be specific and concise; no preamble."
)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


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
    """Parse the model reply into an EstimateResult, tolerating code fences and
    surrounding prose (for models without structured-output support)."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return EstimateResult.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError):
        match = _JSON_BLOCK.search(text)
        if match is None:
            raise ValueError("no JSON object found in model response") from None
        return EstimateResult.model_validate(json.loads(match.group(0)))


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
    lines = []
    for q in questions:
        required = ", required" if q.is_required else ""
        lines.append(f"- [{q.type.value}{required}] {q.prompt}")
        if q.options:
            lines.append(f"  options: {' | '.join(o.label for o in q.options)}")
    body = "\n".join(lines) if lines else "(no questions yet)"
    return [
        {"role": "system", "content": ADVICE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Injury type: {injury_type.name}\n\nCurrent questionnaire:\n{body}",
        },
    ]


async def generate_advice(db: AsyncSession, injury_type: InjuryType) -> EstimateAdvice:
    """Ask the model what the questionnaire should collect; upsert the result."""
    app_settings = await get_app_settings(db)
    if not ai_configured(app_settings):
        raise AppError(400, "ai_not_configured", "Configure the OpenRouter key and model first")
    questions = list(
        await db.scalars(
            select(Question)
            .where(Question.injury_type_id == injury_type.id)
            .order_by(Question.display_order)
            .options(selectinload(Question.options))
        )
    )
    try:
        content = await openrouter.chat_completion(
            app_settings.openrouter_api_key,
            app_settings.openrouter_model,
            _advice_messages(injury_type, questions),
            referer=app_settings.app_base_url,
        )
    except OpenRouterError as exc:
        raise AppError(502, exc.code, exc.message) from exc
    advice = await db.scalar(
        select(EstimateAdvice).where(EstimateAdvice.injury_type_id == injury_type.id)
    )
    if advice is None:
        advice = EstimateAdvice(injury_type_id=injury_type.id, content=content)
        db.add(advice)
    else:
        advice.content = content
    advice.model = app_settings.openrouter_model
    await db.commit()
    await db.refresh(advice)
    return advice
