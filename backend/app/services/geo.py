"""US states + counties reference data.

The bundled dataset is the official Census 2020 county list (50 states + DC,
3,143 counties and county-equivalents), shipped as ``app/data/us_counties.json``
and seeded into the ``us_counties`` table for querying. The in-memory copy
backs answer validation without a round-trip per keystroke.
"""

import json
from functools import lru_cache
from importlib import resources

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsCounty


@lru_cache(maxsize=1)
def counties_by_state() -> dict[str, list[str]]:
    raw = resources.files("app.data").joinpath("us_counties.json").read_text("utf-8")
    return json.loads(raw)


def is_valid_state(code: str) -> bool:
    return code in counties_by_state()


def is_valid_county(state_code: str, county: str) -> bool:
    return county in counties_by_state().get(state_code, [])


async def seed_us_counties(db: AsyncSession) -> int:
    """Bulk-insert the county list if the table is empty. Returns rows added."""
    existing = await db.scalar(select(func.count()).select_from(UsCounty))
    if existing:
        return 0
    rows = [
        UsCounty(state_code=state, name=name)
        for state, names in counties_by_state().items()
        for name in names
    ]
    db.add_all(rows)
    return len(rows)
