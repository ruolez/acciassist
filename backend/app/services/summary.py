import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import IntakeAnswer, IntakeSession, Question, QuestionType, SummaryTemplate
from app.schemas import SummaryOut

# Matches {{ slug }} with optional surrounding whitespace.
_TOKEN = re.compile(r"\{\{\s*([a-zA-Z0-9_-]+)\s*\}\}")


def answer_display_value(
    question_type: QuestionType,
    raw_value: object,
    option_labels: dict[str, str] | None = None,
) -> str:
    """Convert a stored answer value into human-readable text for the summary."""
    labels = option_labels or {}
    if raw_value is None:
        return ""
    if question_type == QuestionType.yes_no:
        return "Yes" if raw_value else "No"
    if question_type == QuestionType.multi_choice:
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        return ", ".join(labels.get(str(v), str(v)) for v in values)
    if question_type == QuestionType.single_choice:
        return labels.get(str(raw_value), str(raw_value))
    if question_type == QuestionType.us_state_county:
        # Stored as ["CA"] or ["CA", "San Bernardino County"].
        parts = raw_value if isinstance(raw_value, list) else [raw_value]
        if len(parts) >= 2:
            return f"{parts[1]}, {parts[0]}"
        return str(parts[0]) if parts else ""
    return str(raw_value)


def render_template(body: str, values: dict[str, str]) -> str:
    """Replace ``{{ slug }}`` tokens in ``body`` with values; unknown slugs become empty."""
    return _TOKEN.sub(lambda m: values.get(m.group(1), ""), body)


async def render_session_summary(db: AsyncSession, session: IntakeSession) -> SummaryOut:
    """Render the intake session's summary template with its answers filled in."""
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
    values: dict[str, str] = {}
    for q in questions:
        labels = {o.value: o.label for o in q.options}
        values[q.slug] = answer_display_value(q.type, answers.get(q.id), labels)

    tmpl = await db.scalar(
        select(SummaryTemplate).where(SummaryTemplate.injury_type_id == session.injury_type_id)
    )
    if tmpl is None:
        return SummaryOut(
            body="",
            estimate_min=None,
            estimate_max=None,
            estimate_note="Upon closer inspection our experts will provide a better estimate.",
        )
    return SummaryOut(
        body=render_template(tmpl.body, values),
        estimate_min=tmpl.estimate_min,
        estimate_max=tmpl.estimate_max,
        estimate_note=tmpl.estimate_note,
    )
