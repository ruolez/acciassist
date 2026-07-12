from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DbSession
from app.errors import AppError
from app.models import JurisdictionRule
from app.schemas import JurisdictionRuleIn, JurisdictionRuleOut
from app.services.estimate_pipeline.jurisdiction_data import seed_jurisdiction_defaults

router = APIRouter()


@router.get("", response_model=list[JurisdictionRuleOut])
async def list_jurisdictions(db: DbSession) -> list[JurisdictionRule]:
    rows = list(
        await db.scalars(select(JurisdictionRule).order_by(JurisdictionRule.state_code))
    )
    if not rows:
        # First read on an installation whose seed predates this feature.
        await seed_jurisdiction_defaults(db)
        await db.commit()
        rows = list(
            await db.scalars(select(JurisdictionRule).order_by(JurisdictionRule.state_code))
        )
    return rows


@router.put("/{state_code}", response_model=JurisdictionRuleOut)
async def update_jurisdiction(
    state_code: str, data: JurisdictionRuleIn, db: DbSession
) -> JurisdictionRule:
    row = await db.get(JurisdictionRule, state_code.upper())
    if row is None:
        raise AppError(404, "not_found", f"No jurisdiction rule for '{state_code}'")
    row.comparative_rule = data.comparative_rule
    row.no_fault = data.no_fault
    row.pip_threshold_note = data.pip_threshold_note
    row.sol_years_pi = data.sol_years_pi
    row.sol_note = data.sol_note
    row.noneconomic_cap = data.noneconomic_cap
    row.cap_note = data.cap_note
    row.collateral_source_note = data.collateral_source_note
    row.needs_review = data.needs_review
    await db.commit()
    await db.refresh(row)
    return row
