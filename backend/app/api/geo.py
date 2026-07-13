"""Public US geography reference endpoints for the intake wizard."""

from fastapi import APIRouter

from app.errors import AppError
from app.services.estimate_pipeline.jurisdiction_data import JURISDICTION_DEFAULTS
from app.services.geo import counties_by_state

router = APIRouter()

_STATES = [
    {"code": row["state_code"], "name": row["state_name"]} for row in JURISDICTION_DEFAULTS
]


@router.get("/geo/states")
async def list_states() -> list[dict]:
    return _STATES


@router.get("/geo/counties/{state_code}")
async def list_counties(state_code: str) -> list[str]:
    counties = counties_by_state().get(state_code.upper())
    if counties is None:
        raise AppError(404, "not_found", "Unknown state code")
    return counties
