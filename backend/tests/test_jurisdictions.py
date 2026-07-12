from app.models import JurisdictionRule
from app.services.estimate_pipeline.jurisdiction_data import (
    COMPARATIVE_RULES,
    JURISDICTION_DEFAULTS,
    seed_jurisdiction_defaults,
)


def test_defaults_cover_50_states_plus_dc():
    codes = [r["state_code"] for r in JURISDICTION_DEFAULTS]
    assert len(codes) == 51
    assert len(set(codes)) == 51
    assert "DC" in codes
    assert all(r["comparative_rule"] in COMPARATIVE_RULES for r in JURISDICTION_DEFAULTS)
    assert all(r["needs_review"] is True for r in JURISDICTION_DEFAULTS)
    assert all(0 < r["sol_years_pi"] <= 20 for r in JURISDICTION_DEFAULTS)


async def test_seed_is_idempotent_and_preserves_edits(session_factory):
    async with session_factory() as db:
        assert await seed_jurisdiction_defaults(db) == 51
        await db.commit()

    async with session_factory() as db:
        row = await db.get(JurisdictionRule, "CA")
        row.sol_years_pi = 7.5
        row.needs_review = False
        await db.commit()

    async with session_factory() as db:
        assert await seed_jurisdiction_defaults(db) == 0
        await db.commit()
        edited = await db.get(JurisdictionRule, "CA")
        assert edited.sol_years_pi == 7.5
        assert edited.needs_review is False


async def test_list_seeds_lazily_and_orders_by_code(admin_client):
    resp = await admin_client.get("/api/admin/jurisdictions")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 51
    assert [r["state_code"] for r in rows] == sorted(r["state_code"] for r in rows)
    fl = next(r for r in rows if r["state_code"] == "FL")
    assert fl["no_fault"] is True
    assert fl["needs_review"] is True


async def test_update_rule_roundtrip(admin_client, session_factory):
    async with session_factory() as db:
        await seed_jurisdiction_defaults(db)
        await db.commit()
    payload = {
        "comparative_rule": "modified_51",
        "no_fault": True,
        "pip_threshold_note": "verified note",
        "sol_years_pi": 2.0,
        "sol_note": None,
        "noneconomic_cap": 500000,
        "cap_note": None,
        "collateral_source_note": None,
        "needs_review": False,
    }
    resp = await admin_client.put("/api/admin/jurisdictions/fl", json=payload)
    assert resp.status_code == 200
    saved = resp.json()
    assert saved["state_code"] == "FL"
    assert saved["noneconomic_cap"] == 500000
    assert saved["needs_review"] is False


async def test_update_validates_rule_and_state(admin_client, session_factory):
    async with session_factory() as db:
        await seed_jurisdiction_defaults(db)
        await db.commit()
    bad_rule = {"comparative_rule": "vibes", "sol_years_pi": 2.0}
    resp = await admin_client.put("/api/admin/jurisdictions/CA", json=bad_rule)
    assert resp.status_code == 422

    ok = {"comparative_rule": "pure", "sol_years_pi": 2.0}
    resp = await admin_client.put("/api/admin/jurisdictions/ZZ", json=ok)
    assert resp.status_code == 404


async def test_jurisdictions_require_admin_auth(client):
    resp = await client.get("/api/admin/jurisdictions")
    assert resp.status_code == 401
