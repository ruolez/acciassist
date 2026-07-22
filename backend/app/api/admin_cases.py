from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import CurrentAdmin, DbSession
from app.errors import AppError
from app.models import (
    STAGE_LABELS,
    Case,
    CaseDocument,
    CaseEstimate,
    CaseStage,
    CaseUpdate,
    CaseUpdateKind,
    InjuryType,
    IntakeSession,
    TokenPurpose,
)
from app.schemas import (
    AdminCaseDetailOut,
    AdminCaseListOut,
    AdminCaseUpdateOut,
    CaseDocumentOut,
    CaseEstimateAdminOut,
    CaseStageIn,
    CaseUpdateIn,
)
from app.services.case_purge import purge_case
from app.services.documents import delete_stored_file, document_path
from app.services.leads import issue_token
from app.services.notifications import (
    notify_case_update,
    notify_lead_received,
    notify_stage_changed,
)

router = APIRouter()


async def _injury_type_info(db: DbSession, case: Case) -> tuple[int | None, str | None]:
    if case.lead.intake_session_id is None:
        return None, None
    row = (
        await db.execute(
            select(InjuryType.id, InjuryType.name)
            .select_from(IntakeSession)
            .join(InjuryType, InjuryType.id == IntakeSession.injury_type_id)
            .where(IntakeSession.id == case.lead.intake_session_id)
        )
    ).first()
    return (row.id, row.name) if row else (None, None)


def _list_row(case: Case, injury_type_name: str | None) -> dict:
    return {
        "id": case.id,
        "stage": case.stage,
        "created_at": case.created_at,
        "lead_name": case.lead.name,
        "lead_email": case.lead.email,
        "lead_phone": case.lead.phone,
        "user_claimed": case.user.password_hash is not None,
        "injury_type_name": injury_type_name,
    }


async def _load_case(db: DbSession, case_id: int, with_updates: bool = False) -> Case:
    options = [selectinload(Case.lead), selectinload(Case.user)]
    if with_updates:
        options.append(selectinload(Case.updates).selectinload(CaseUpdate.admin))
    case = await db.scalar(select(Case).where(Case.id == case_id).options(*options))
    if case is None:
        raise AppError(404, "not_found", "Case not found")
    return case


@router.get("/cases", response_model=list[AdminCaseListOut])
async def list_cases(
    db: DbSession, stage: CaseStage | None = None
) -> list[AdminCaseListOut]:
    query = (
        select(Case)
        .order_by(Case.created_at.desc())
        .options(selectinload(Case.lead), selectinload(Case.user))
    )
    if stage is not None:
        query = query.where(Case.stage == stage)
    cases = await db.scalars(query)
    return [
        AdminCaseListOut(**_list_row(case, (await _injury_type_info(db, case))[1]))
        for case in cases
    ]


@router.get("/cases/{case_id}", response_model=AdminCaseDetailOut)
async def case_detail(case_id: int, db: DbSession) -> AdminCaseDetailOut:
    case = await _load_case(db, case_id, with_updates=True)
    estimate = None
    if case.lead.intake_session_id is not None:
        estimate = await db.scalar(
            select(CaseEstimate).where(
                CaseEstimate.intake_session_id == case.lead.intake_session_id
            )
        )
    injury_type_id, injury_type_name = await _injury_type_info(db, case)
    return AdminCaseDetailOut(
        **_list_row(case, injury_type_name),
        injury_type_id=injury_type_id,
        intake_session_id=case.lead.intake_session_id,
        estimate=CaseEstimateAdminOut.model_validate(estimate) if estimate else None,
        updates=[
            AdminCaseUpdateOut(
                id=u.id,
                kind=u.kind,
                body=u.body,
                created_at=u.created_at,
                admin_email=u.admin.email if u.admin else None,
            )
            for u in case.updates
        ],
    )


@router.patch("/cases/{case_id}", response_model=AdminCaseDetailOut)
async def change_stage(
    case_id: int,
    data: CaseStageIn,
    admin: CurrentAdmin,
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> AdminCaseDetailOut:
    case = await _load_case(db, case_id)
    if data.stage != case.stage:
        case.stage = data.stage
        db.add(
            CaseUpdate(
                case_id=case.id,
                admin_id=admin.id,
                kind=CaseUpdateKind.stage_change,
                body=f"Stage changed to {STAGE_LABELS[data.stage]}",
            )
        )
        await db.commit()
        background_tasks.add_task(notify_stage_changed, case.id)
    return await case_detail(case_id, db)


@router.post("/cases/{case_id}/updates", response_model=AdminCaseDetailOut, status_code=201)
async def post_update(
    case_id: int,
    data: CaseUpdateIn,
    admin: CurrentAdmin,
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> AdminCaseDetailOut:
    case = await _load_case(db, case_id)
    db.add(
        CaseUpdate(
            case_id=case.id,
            admin_id=admin.id,
            kind=CaseUpdateKind.message,
            body=data.body,
        )
    )
    await db.commit()
    background_tasks.add_task(notify_case_update, case.id)
    return await case_detail(case_id, db)


@router.post("/cases/{case_id}/resend-invite")
async def resend_invite(
    case_id: int, db: DbSession, background_tasks: BackgroundTasks
) -> dict[str, bool]:
    case = await _load_case(db, case_id)
    if case.user.password_hash is not None:
        raise AppError(409, "already_claimed", "This client has already created an account")
    raw = await issue_token(db, case.user_id, TokenPurpose.account_claim)
    await db.commit()
    background_tasks.add_task(notify_lead_received, case.lead_id, raw)
    return {"ok": True}


@router.get("/cases/{case_id}/documents", response_model=list[CaseDocumentOut])
async def case_documents(case_id: int, db: DbSession) -> list[CaseDocument]:
    await _load_case(db, case_id)
    rows = await db.scalars(
        select(CaseDocument)
        .where(CaseDocument.case_id == case_id)
        .order_by(CaseDocument.created_at.desc())
    )
    return list(rows)


@router.delete("/cases/{case_id}", status_code=204)
async def delete_case(case_id: int, db: DbSession) -> None:
    """Hard-delete a case and everything attached: documents (rows + stored
    files), updates, the lead, and the lead's intake session with answers and
    estimate. The User row is kept (unique email; may be claimed or own other
    cases). email_log.case_id nulls out via FK."""
    case = await db.scalar(
        select(Case)
        .where(Case.id == case_id)
        .options(
            selectinload(Case.lead),
            selectinload(Case.documents),
            selectinload(Case.updates),
        )
    )
    if case is None:
        raise AppError(404, "not_found", "Case not found")
    docs = await purge_case(db, case)
    await db.commit()
    for doc in docs:
        delete_stored_file(doc)


@router.get("/cases/{case_id}/documents/{doc_id}/download")
async def download_case_document(case_id: int, doc_id: int, db: DbSession) -> FileResponse:
    await _load_case(db, case_id)
    doc = await db.get(CaseDocument, doc_id)
    if doc is None or doc.case_id != case_id:
        raise AppError(404, "not_found", "Document not found")
    path = document_path(doc)
    if not path.exists():
        raise AppError(404, "file_missing", "The stored file is missing.")
    return FileResponse(path, media_type=doc.content_type, filename=doc.original_name)
