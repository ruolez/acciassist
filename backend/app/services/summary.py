import re

from app.models import QuestionType

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
    return str(raw_value)


def render_template(body: str, values: dict[str, str]) -> str:
    """Replace ``{{ slug }}`` tokens in ``body`` with values; unknown slugs become empty."""
    return _TOKEN.sub(lambda m: values.get(m.group(1), ""), body)
