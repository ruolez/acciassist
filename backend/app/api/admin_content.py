from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DbSession
from app.errors import AppError
from app.models import InjuryType, Question, SummaryTemplate
from app.schemas import (
    InjuryTypeIn,
    InjuryTypeOut,
    QuestionIn,
    QuestionLayoutIn,
    QuestionOut,
    ReorderIn,
    SummaryTemplateIn,
    SummaryTemplateOut,
)
from app.services.questions import (
    apply_question_update,
    create_questions,
    load_question,
    next_display_order,
)
from app.services.slugs import slugify_unique

router = APIRouter()


async def _get_injury_type(db: DbSession, injury_type_id: int) -> InjuryType:
    obj = await db.get(InjuryType, injury_type_id)
    if obj is None:
        raise AppError(404, "not_found", "Injury type not found")
    return obj


async def _apply_order(db: DbSession, model, ordered_ids: list[int], **filters) -> None:
    stmt = select(model)
    for attr, val in filters.items():
        stmt = stmt.where(getattr(model, attr) == val)
    rows = {row.id: row for row in (await db.scalars(stmt)).all()}
    if set(ordered_ids) != set(rows.keys()):
        raise AppError(400, "invalid_reorder", "ordered_ids must match exactly the existing items")
    for index, item_id in enumerate(ordered_ids):
        rows[item_id].display_order = index


# ── Injury types ───────────────────────────────────────────────────────
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
        display_order=await next_display_order(db, InjuryType),
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


# ── Questions ──────────────────────────────────────────────────────────
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
    (question,) = await create_questions(db, injury_type_id, [data])
    await db.commit()
    return await load_question(db, injury_type_id, question.id)


# Registered before the {question_id} routes so the literal "layout" segment
# isn't swallowed by the int path parameter.
@router.put("/injury-types/{injury_type_id}/questions/layout", status_code=204)
async def set_question_layout(
    injury_type_id: int, data: QuestionLayoutIn, db: DbSession
) -> None:
    """Persist the wizard page structure: display_order follows the flattened
    page list, and page_group encodes grouping the way build_pages expects —
    single-question pages get None, multi-question pages get their page index
    (adjacent pages therefore always differ, so runs never merge by accident).
    """
    await _get_injury_type(db, injury_type_id)
    rows = {
        row.id: row
        for row in await db.scalars(
            select(Question).where(Question.injury_type_id == injury_type_id)
        )
    }
    flat = [qid for page in data.pages for qid in page]
    if set(flat) != set(rows.keys()):
        raise AppError(
            400, "invalid_layout", "pages must contain exactly the existing question ids"
        )
    for index, qid in enumerate(flat):
        rows[qid].display_order = index
    for page_index, page in enumerate(data.pages):
        group = page_index if len(page) > 1 else None
        for qid in page:
            rows[qid].page_group = group
    await db.commit()


@router.put(
    "/injury-types/{injury_type_id}/questions/{question_id}",
    response_model=QuestionOut,
)
async def update_question(
    injury_type_id: int, question_id: int, data: QuestionIn, db: DbSession
) -> Question:
    question = await load_question(db, injury_type_id, question_id)
    # page_group is deliberately not writable here — the layout endpoint owns it,
    # so saving a question can never scramble the page structure.
    apply_question_update(question, data)
    await db.commit()
    return await load_question(db, injury_type_id, question_id)


@router.delete(
    "/injury-types/{injury_type_id}/questions/{question_id}", status_code=204
)
async def delete_question(injury_type_id: int, question_id: int, db: DbSession) -> None:
    question = await load_question(db, injury_type_id, question_id)
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




# ── Summary template ───────────────────────────────────────────────────
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
