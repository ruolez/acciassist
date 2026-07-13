"""US states/counties reference data + the us_state_county question type."""

from app.models import QuestionType, UsCounty
from app.services.geo import counties_by_state, is_valid_county, seed_us_counties
from app.services.summary import answer_display_value


class TestDataset:
    def test_covers_50_states_plus_dc_with_census_counts(self):
        data = counties_by_state()
        assert len(data) == 51
        assert sum(len(v) for v in data.values()) == 3143  # Census 2020 count
        assert "San Bernardino County" in data["CA"]
        assert "District of Columbia" in data["DC"]
        assert len(data["TX"]) == 254  # most counties of any state

    def test_county_validation(self):
        assert is_valid_county("CA", "San Bernardino County") is True
        assert is_valid_county("CA", "Bexar County") is False
        assert is_valid_county("ZZ", "Anything") is False


async def test_seed_us_counties_is_idempotent(session_factory):
    async with session_factory() as db:
        assert await seed_us_counties(db) == 3143
        await db.commit()
    async with session_factory() as db:
        assert await seed_us_counties(db) == 0
        row = await db.get(UsCounty, 1)
        assert row is not None


async def test_geo_endpoints(client):
    states = (await client.get("/api/geo/states")).json()
    assert len(states) == 51
    assert {"code": "CA", "name": "California"} in states

    counties = (await client.get("/api/geo/counties/ca")).json()
    assert "Los Angeles County" in counties

    resp = await client.get("/api/geo/counties/ZZ")
    assert resp.status_code == 404


async def _location_intake(admin_client) -> tuple[str, int]:
    itid = (
        await admin_client.post(
            "/api/admin/injury-types", json={"name": "Auto", "is_published": True}
        )
    ).json()["id"]
    q = (
        await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "us_state_county", "prompt": "Where did it happen?"},
        )
    ).json()
    sid = (
        await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
    ).json()["session_id"]
    return sid, q["id"]


class TestAnswerValidation:
    async def test_valid_state_and_county_accepted(self, admin_client):
        sid, qid = await _location_intake(admin_client)
        resp = await admin_client.post(
            f"/api/intake/{sid}/answers",
            json={"answers": [{"question_id": qid, "value": ["CA", "San Bernardino County"]}]},
        )
        assert resp.status_code == 204

    async def test_state_only_accepted(self, admin_client):
        sid, qid = await _location_intake(admin_client)
        resp = await admin_client.post(
            f"/api/intake/{sid}/answers",
            json={"answers": [{"question_id": qid, "value": ["NY"]}]},
        )
        assert resp.status_code == 204

    async def test_invalid_shapes_rejected(self, admin_client):
        sid, qid = await _location_intake(admin_client)
        for bad in (
            "CA",
            ["ZZ"],
            ["CA", "Bexar County"],  # Texas county under CA
            ["CA", "San Bernardino County", "extra"],
            [],
        ):
            resp = await admin_client.post(
                f"/api/intake/{sid}/answers",
                json={"answers": [{"question_id": qid, "value": bad}]},
            )
            assert resp.status_code == 422, bad


def test_display_value_renders_county_and_state():
    t = QuestionType.us_state_county
    assert answer_display_value(t, ["CA", "San Bernardino County"]) == (
        "San Bernardino County, CA"
    )
    assert answer_display_value(t, ["NY"]) == "NY"
    assert answer_display_value(t, None) == ""
