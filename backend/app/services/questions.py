"""Question create/update mechanics shared by the admin CRUD endpoints and the
AI proposal apply flow. Nothing here commits — callers own the transaction.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import AppError
from app.models import Question, QuestionOption
from app.schemas import QuestionIn, QuestionOptionIn
from app.services.slugs import slugify_unique


async def next_display_order(db: AsyncSession, model, **filters) -> int:
    stmt = select(func.coalesce(func.max(model.display_order), -1))
    for attr, val in filters.items():
        stmt = stmt.where(getattr(model, attr) == val)
    current_max = await db.scalar(stmt)
    return int(current_max) + 1


def replace_options(question: Question, options: list[QuestionOptionIn]) -> None:
    question.options = [
        QuestionOption(label=o.label, value=o.value, display_order=i)
        for i, o in enumerate(options)
    ]


async def load_question(db: AsyncSession, injury_type_id: int, question_id: int) -> Question:
    q = await db.scalar(
        select(Question)
        .where(Question.id == question_id, Question.injury_type_id == injury_type_id)
        .options(selectinload(Question.options))
    )
    if q is None:
        raise AppError(404, "not_found", "Question not found")
    return q


async def create_questions(
    db: AsyncSession, injury_type_id: int, drafts: list[QuestionIn]
) -> list[Question]:
    """Batch-safe creation: slugs from earlier drafts count as taken for later
    ones, and display_order continues past the current maximum in draft order."""
    taken = set(
        await db.scalars(
            select(Question.slug).where(Question.injury_type_id == injury_type_id)
        )
    )
    order = await next_display_order(db, Question, injury_type_id=injury_type_id)
    created: list[Question] = []
    for data in drafts:
        slug = slugify_unique(data.prompt, taken)
        taken.add(slug)
        question = Question(
            injury_type_id=injury_type_id,
            slug=slug,
            type=data.type,
            phase=data.phase,
            prompt=data.prompt,
            help_text=data.help_text,
            is_required=data.is_required,
            config=data.config.model_dump(exclude_none=True),
            display_order=order,
        )
        order += 1
        replace_options(question, data.options)
        db.add(question)
        created.append(question)
    return created


def apply_question_update(question: Question, data: QuestionIn) -> None:
    """Same semantics as the admin PUT: rewrite fields and replace options.
    slug, page_group, and display_order are never touched."""
    question.type = data.type
    question.phase = data.phase
    question.prompt = data.prompt
    question.help_text = data.help_text
    question.is_required = data.is_required
    question.config = data.config.model_dump(exclude_none=True)
    replace_options(question, data.options)
