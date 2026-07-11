import pytest

from app.config import Settings, settings

ADMIN_EMAIL = "tester@example.com"
STRONG_SECRET = "a" * 40
STRONG_PASSWORD = "a-real-production-password"
PROD_DB_URL = "postgresql+asyncpg://acciassist:realpass@db:5432/acciassist"


class TestProductionConfigGuard:
    def test_rejects_dev_defaults_in_production(self):
        with pytest.raises(ValueError, match="JWT_SECRET"):
            Settings(
                app_env="production",
                jwt_secret="dev-only-insecure-secret-change-me",
                admin_password=STRONG_PASSWORD,
                database_url=PROD_DB_URL,
            )
        with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
            Settings(
                app_env="production",
                jwt_secret=STRONG_SECRET,
                admin_password="changeme123",
                database_url=PROD_DB_URL,
            )
        with pytest.raises(ValueError, match="DATABASE_URL"):
            Settings(
                app_env="production",
                jwt_secret=STRONG_SECRET,
                admin_password=STRONG_PASSWORD,
                database_url="postgresql+asyncpg://acciassist:change-me-in-prod@db:5432/acciassist",
            )

    def test_short_jwt_secret_rejected_in_production(self):
        with pytest.raises(ValueError, match="JWT_SECRET"):
            Settings(
                app_env="production",
                jwt_secret="short",
                admin_password=STRONG_PASSWORD,
                database_url=PROD_DB_URL,
            )

    def test_dev_defaults_allowed_outside_production(self):
        cfg = Settings(
            app_env="development",
            jwt_secret="dev-only-insecure-secret-change-me",
            admin_password="changeme123",
        )
        assert cfg.is_production is False

    def test_strong_production_settings_accepted(self):
        cfg = Settings(
            app_env="production",
            jwt_secret=STRONG_SECRET,
            admin_password=STRONG_PASSWORD,
            database_url=PROD_DB_URL,
        )
        assert cfg.is_production is True


async def test_login_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    statuses = []
    for _ in range(6):
        resp = await client.post(
            "/api/admin/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"}
        )
        statuses.append(resp.status_code)
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    body = resp.json()
    assert body["error"]["code"] == "rate_limited"


async def _intake_with_questions(admin_client):
    resp = await admin_client.post(
        "/api/admin/injury-types", json={"name": "Auto Accident", "is_published": True}
    )
    itid = resp.json()["id"]
    questions = {}
    for payload in (
        {
            "type": "single_choice",
            "prompt": "Driver or passenger?",
            "options": [
                {"label": "Driver", "value": "driver"},
                {"label": "Passenger", "value": "passenger"},
            ],
        },
        {"type": "yes_no", "prompt": "Injured?"},
        {"type": "short_text", "prompt": "Name?"},
        {"type": "number", "prompt": "Vehicles involved?"},
        {"type": "date", "prompt": "When?"},
    ):
        q = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions", json=payload
        )
        questions[payload["type"]] = q.json()
    start = (
        await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
    ).json()
    return start["session_id"], questions


class TestAnswerValidation:
    async def _save(self, client, sid, question_id, value):
        return await client.post(
            f"/api/intake/{sid}/answers",
            json={"answers": [{"question_id": question_id, "value": value}]},
        )

    async def test_rejects_wrong_shapes_per_question_type(self, admin_client):
        sid, questions = await _intake_with_questions(admin_client)
        cases = [
            (questions["single_choice"], "not-an-option"),
            (questions["single_choice"], ["driver"]),
            (questions["yes_no"], "yes"),
            (questions["short_text"], True),
            (questions["number"], "three"),
            (questions["number"], True),
            (questions["date"], "not-a-date"),
        ]
        for question, bad_value in cases:
            resp = await self._save(admin_client, sid, question["id"], bad_value)
            assert resp.status_code == 422, (question["type"], bad_value, resp.text)
            assert resp.json()["error"]["code"] == "invalid_answer"

    async def test_rejects_question_from_other_injury_type(self, admin_client):
        sid, _ = await _intake_with_questions(admin_client)
        other = await admin_client.post(
            "/api/admin/injury-types", json={"name": "Other", "is_published": True}
        )
        foreign_q = await admin_client.post(
            f"/api/admin/injury-types/{other.json()['id']}/questions",
            json={"type": "short_text", "prompt": "Foreign?"},
        )
        resp = await self._save(admin_client, sid, foreign_q.json()["id"], "hello")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_answer"

    async def test_rejects_oversized_values(self, admin_client):
        sid, questions = await _intake_with_questions(admin_client)
        resp = await self._save(
            admin_client, sid, questions["short_text"]["id"], "x" * 20_000
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    async def test_valid_answers_still_accepted(self, admin_client):
        sid, questions = await _intake_with_questions(admin_client)
        good = [
            (questions["single_choice"], "driver"),
            (questions["yes_no"], True),
            (questions["short_text"], "Pat"),
            (questions["number"], 2),
            (questions["date"], "2026-07-01"),
            (questions["short_text"], None),
        ]
        for question, value in good:
            resp = await self._save(admin_client, sid, question["id"], value)
            assert resp.status_code == 204, (question["type"], value, resp.text)


async def _intake_with_configured_questions(admin_client):
    resp = await admin_client.post(
        "/api/admin/injury-types", json={"name": "Auto Accident", "is_published": True}
    )
    itid = resp.json()["id"]
    questions = {}
    for payload in (
        {"type": "number", "prompt": "Vehicles involved?", "config": {"min": 1, "max": 10}},
        {"type": "date", "prompt": "When?", "config": {"disallow_future": True}},
        {"type": "short_text", "prompt": "Name?", "config": {"max_length": 20}},
    ):
        q = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions", json=payload
        )
        assert q.status_code == 201, q.text
        questions[payload["type"]] = q.json()
    start = (
        await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
    ).json()
    return itid, start["session_id"], questions


class TestConfigBounds:
    async def _save(self, client, sid, question_id, value):
        return await client.post(
            f"/api/intake/{sid}/answers",
            json={"answers": [{"question_id": question_id, "value": value}]},
        )

    async def test_number_bounds_enforced_with_boundaries_allowed(self, admin_client):
        _, sid, questions = await _intake_with_configured_questions(admin_client)
        qid = questions["number"]["id"]
        for value, expected in ((0, 422), (11, 422), (1, 204), (10, 204)):
            resp = await self._save(admin_client, sid, qid, value)
            assert resp.status_code == expected, (value, resp.text)
            if expected == 422:
                assert resp.json()["error"]["code"] == "invalid_answer"

    async def test_future_date_rejected_today_allowed(self, admin_client):
        from datetime import date, timedelta

        _, sid, questions = await _intake_with_configured_questions(admin_client)
        qid = questions["date"]["id"]
        future = (date.today() + timedelta(days=30)).isoformat()
        assert (await self._save(admin_client, sid, qid, future)).status_code == 422
        assert (
            await self._save(admin_client, sid, qid, date.today().isoformat())
        ).status_code == 204

    async def test_text_max_length_enforced(self, admin_client):
        _, sid, questions = await _intake_with_configured_questions(admin_client)
        qid = questions["short_text"]["id"]
        assert (await self._save(admin_client, sid, qid, "x" * 21)).status_code == 422
        assert (await self._save(admin_client, sid, qid, "x" * 20)).status_code == 204

    async def test_legacy_junk_config_is_tolerated(self, admin_client, session_factory):
        from sqlalchemy import update

        from app.models import Question

        _, sid, questions = await _intake_with_configured_questions(admin_client)
        qid = questions["number"]["id"]
        async with session_factory() as s:
            await s.execute(
                update(Question)
                .where(Question.id == qid)
                .values(config={"min": "abc", "max": None, "weird": [1, 2]})
            )
            await s.commit()
        resp = await self._save(admin_client, sid, qid, 999)
        assert resp.status_code == 204, resp.text

    async def test_invalid_config_rejected_and_unknown_keys_stripped(self, admin_client):
        resp = await admin_client.post(
            "/api/admin/injury-types", json={"name": "Other", "is_published": False}
        )
        itid = resp.json()["id"]
        bad_type = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "number", "prompt": "N?", "config": {"min": "abc"}},
        )
        assert bad_type.status_code == 422
        inverted = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "number", "prompt": "N?", "config": {"min": 5, "max": 2}},
        )
        assert inverted.status_code == 422
        stripped = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "number", "prompt": "N?", "config": {"min": 1, "bogus": True}},
        )
        assert stripped.status_code == 201
        assert stripped.json()["config"] == {"min": 1}
