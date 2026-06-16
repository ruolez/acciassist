from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DbSession
from app.errors import AppError
from app.models import InjuryType, Question, QuestionOption, SummaryTemplate
from app.schemas import (
    InjuryTypeIn,
    InjuryTypeOut,
    QuestionIn,
    QuestionOut,
    ReorderIn,
    SummaryTemplateIn,
    SummaryTemplateOut,
)
from app.services.slugs import slugify_unique

router = APIRouter()


async def _get_injury_type(db: DbSession, injury_type_id: int) -> InjuryType:
    obj = await db.get(InjuryType, injury_type_id)
    if obj is None:
        raise AppError(404, "not_found", "Injury type not found")
    return obj


async def _next_order(db: DbSession, model, **filters) -> int:
    stmt = select(func.coalesce(func.max(model.display_order), -1))
    for attr, val in filters.items():
        stmt = stmt.where(getattr(model, attr) == val)
    current_max = await db.scalar(stmt)
    return int(current_max) + 1


async def _apply_order(db: DbSession, model, ordered_ids: list[int], **filters) -> None:
    stmt = select(model)
    for attr, val in filters.items():
        stmt = stmt.where(getattr(model, attr) == val)
    rows = {row.id: row for row in (await db.scalars(stmt)).all()}
    if set(ordered_ids) != set(rows.keys()):
        raise AppError(400, "invalid_reorder", "ordered_ids must match exactly the existing items")
    for index, item_id in enumerate(ordered_ids):
        rows[item_id].display_order = index


# ── Injury types ───────────────────────────────────────────────────────────────
@router.get("/injury-types", response_model=list[InjuryTypeOut])
async def list_injury_types(db: DbSession) -> list[InjuryType]:
    rows = await db.scalars(select(InjuryType).order_by(InjuryType.display_order))
    return list(rows)


@router.post("/injury-types", response_model=InjuryTypeOut, status_code=201)
async def create_injury_type(data: InjuryTypeIn, db: DbSession) -> InjuryType:
    existing_slugs = list(await db.scalars(select(InjuryType.slug)))
    obj = InjuryType(
        slug=slugify_unique(data.name, existing_slugs),
        name=data.name,
        description=data.description,
        is_published=data.is_published,
        display_order=await _next_order(db, InjuryType),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.put("/injury-types/{injury_type_id}", response_model=InjuryTypeOut)
async def update_injury_type(
    injury_type_id: int, data: InjuryTypeIn, db: DbSession
) -> InjuryType:
    obj = await _get_injury_type(db, injury_type_id)
    obj.name = data.name
    obj.description = data.description
    obj.is_published = data.is_published
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/injury-types/{injury_type_id}", status_code=204)
async def delete_injury_type(injury_type_id: int, db: DbSession) -> None:
    obj = await _get_injury_type(db, injury_type_id)
    await db.delete(obj)
    await db.commit()


@router.post("/injury-types/reorder", status_code=204)
async def reorder_injury_types(data: ReorderIn, db: DbSession) -> None:
    await _apply_order(db, InjuryType, data.ordered_ids)
    await db.commit()


# ── Questions ─────────────────────────────────────────────────────────────────
async def _load_question(db: DbSession, injury_type_id: int, question_id: int) -> Question:
    q = await db.scalar(
        select(Question)
        .where(Question.id == question_id, Question.injury_type_id == injury_type_id)
        .options(selectinload(Question.options))
    )
    if q is None:
        raise AppError(404, "not_found", "Question not found")
    return q


def _replace_options(question: Question, options: list) -> None:
    question.options = [
        QuestionOption(label=o.label, value=o.value, display_order=i)
        for i, o in enumerate(options)
    ]


@router.get(
    "/injury-types/{injury_type_id}/questions", response_model=list[QuestionOut]
)
async def list_questions(injury_type_id: int, db: DbSession) -> list[Question]:
    await _get_injury_type(db, injury_type_id)
    rows = await db.scalars(
        select(Question)
        .where(Question.injury_type_id == injury_type_id)
        .order_by(Question.display_order)
        .options(selectinload(Question.options))
    )
    return list(rows)


@router.post(
    "/injury-types/{injury_type_id}/questions",
    response_model=QuestionOut,
    status_code=201,
)
async def create_question(
    injury_type_id: int, data: QuestionIn, db: DbSession
) -> Question:
    await _get_injury_type(db, injury_type_id)
    existing_slugs = list(
        await db.scalars(
            select(Question.slug).where(Question.injury_type_id == injury_type_id)
        )
    )
    question = Question(
        injury_type_id=injury_type_id,
        slug=slugify_unique(data.prompt, existing_slugs),
        type=data.type,
        prompt=data.prompt,
        help_text=data.help_text,
        is_required=data.is_required,
        page_group=data.page_group,
        config=data.config,
        display_order=await _next_order(
            db, Question, injury_type_id=injury_type_id
        ),
    )
    _replace_options(question, data.options)
    db.add(question)
    await db.commit()
    return await _load_question(db, injury_type_id, question.id)


@router.put(
    "/injury-types/{injury_type_id}/questions/{question_id}",
    response_model=QuestionOut,
)
async def update_question(
    injury_type_id: int, question_id: int, data: QuestionIn, db: DbSession
) -> Question:
    question = await _load_question(db, injury_type_id, question_id)
    question.type = data.type
    question.prompt = data.prompt
    question.help_text = data.help_text
    question.is_required = data.is_required
    question.page_group = data.page_group
    question.config = data.config
    _replace_options(question, data.options)
    await db.commit()
    return await _load_question(db, injury_type_id, question_id)


@router.delete(
    "/injury-types/{injury_type_id}/questions/{question_id}", status_code=204
)
async def delete_question(injury_type_id: int, question_id: int, db: DbSession) -> None:
    question = await _load_question(db, injury_type_id, question_id)
    await db.delete(question)
    await db.commit()


@router.post(
    "/injury-types/{injury_type_id}/questions/reorder", status_code=204
)
async def reorder_questions(
    injury_type_id: int, data: ReorderIn, db: DbSession
) -> None:
    await _get_injury_type(db, injury_type_id)
    await _apply_order(db, Question, data.ordered_ids, injury_type_id=injury_type_id)
    await db.commit()


# ── Summary template ────────────────────────────────────────────────────────
async def _get_or_create_template(db: DbSession, injury_type_id: int) -> SummaryTemplate:
    tmpl = await db.scalar(
        select(SummaryTemplate).where(SummaryTemplate.injury_type_id == injury_type_id)
    )
    if tmpl is None:
        tmpl = SummaryTemplate(injury_type_id=injury_type_id, body="")
        db.add(tmpl)
        await db.commit()
        await db.refresh(tmpl)
    return tmpl


@router.get(
    "/injury-types/{injury_type_id}/summary-template",
    response_model=SummaryTemplateOut,
)
async def get_summary_template(injury_type_id: int, db: DbSession) -> SummaryTemplate:
    await _get_injury_type(db, injury_type_id)
    return await _get_or_create_template(db, injury_type_id)


@router.put(
    "/injury-types/{injury_type_id}/summary-template",
    response_model=SummaryTemplateOut,
)
async def update_summary_template(
    injury_type_id: int, data: SummaryTemplateIn, db: DbSession
) -> SummaryTemplate:
    await _get_injury_type(db, injury_type_id)
    tmpl = await _get_or_create_template(db, injury_type_id)
    tmpl.body = data.body
    tmpl.estimate_min = data.estimate_min
    tmpl.estimate_max = data.estimate_max
    tmpl.estimate_note = data.estimate_note
    await db.commit()
    await db.refresh(tmpl)
    return tmpl
