"""Full-depth removal of a case and the records that exist only because of it:
the lead and the lead's intake session (answers via ORM cascade, estimate via
DB CASCADE). The User row is never touched here."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, CaseDocument, IntakeSession


async def purge_case(db: AsyncSession, case: Case) -> list[CaseDocument]:
    """Mark the case, its lead, and its intake session for deletion.

    Requires ``case`` loaded with ``lead``, ``documents``, and ``updates``.
    Returns the documents whose stored files must be unlinked by the caller
    AFTER the surrounding transaction commits — a crash then leaves only
    harmless orphan files, never live rows pointing at deleted files."""
    docs = list(case.documents)
    lead = case.lead
    session_id = lead.intake_session_id
    await db.delete(case)
    await db.delete(lead)
    if session_id is not None:
        intake = await db.get(IntakeSession, session_id)
        if intake is not None:
            await db.delete(intake)
    return docs
