from app.models import Question, QuestionOption, QuestionType
from app.services.estimates import (
    RawAdvice,
    sanitize_proposals,
)
from tests.test_ai_advice import _injury_type_with_question, advice_reply
from tests.test_estimates import seed_ai_settings


def _question(qid: int, prompt: str, qtype=QuestionType.yes_no, options=(), config=None):
    q = Question(
        id=qid,
        injury_type_id=1,
        slug=f"q-{qid}",
        type=qtype,
        prompt=prompt,
        help_text=None,
        is_required=True,
        display_order=qid,
        config=config or {},
    )
    q.options = [
        QuestionOption(id=i + 1, label=label, value=value, display_order=i)
        for i, (label, value) in enumerate(options)
    ]
    return q


def _raw(new_questions=None, question_edits=None) -> RawAdvice:
    return RawAdvice.model_validate(
        {
            "overview": "o",
            "new_questions": new_questions or [],
            "question_edits": question_edits or [],
        }
    )


def _add(prompt, qtype="short_text", options=None, config=None, **extra):
    return {
        "type": qtype,
        "prompt": prompt,
        "options": options or [],
        "config": config or {},
        "rationale": "r",
        **extra,
    }


class TestSanitizeProposals:
    def test_valid_add_gets_sequential_id_and_clean_payload(self):
        out = sanitize_proposals(
            _raw([_add("Bills so far?", "number", config={"min": 0, "max": None})]), []
        )
        assert [p["id"] for p in out] == ["add-1"]
        assert out[0]["payload"]["config"] == {"min": 0}
        assert out[0]["applied"] is False

    def test_choice_without_two_options_dropped(self):
        out = sanitize_proposals(
            _raw(
                [
                    _add("Pick one?", "single_choice", options=[{"label": "Only", "value": "x"}]),
                    _add("Pick two?", "multi_choice", options=[]),
                ]
            ),
            [],
        )
        assert out == []

    def test_non_choice_options_stripped_and_config_pruned_by_type(self):
        out = sanitize_proposals(
            _raw(
                [
                    _add(
                        "When did it happen?",
                        "date",
                        options=[{"label": "Bogus", "value": "bogus"}],
                        config={"disallow_future": True, "min": 1, "max_length": 50},
                    )
                ]
            ),
            [],
        )
        assert out[0]["payload"]["options"] == []
        assert out[0]["payload"]["config"] == {"disallow_future": True}

    def test_option_value_defaults_from_label_and_dedupes(self):
        out = sanitize_proposals(
            _raw(
                [
                    _add(
                        "Which vehicle?",
                        "single_choice",
                        options=[
                            {"label": "My Car!", "value": ""},
                            {"label": "Their car", "value": "my_car"},
                            {"label": "Truck", "value": "truck"},
                        ],
                    )
                ]
            ),
            [],
        )
        values = [o["value"] for o in out[0]["payload"]["options"]]
        assert values == ["my_car", "truck"]

    def test_duplicate_of_existing_prompt_dropped_case_insensitive(self):
        existing = [_question(1, "Were you injured?")]
        out = sanitize_proposals(_raw([_add("were you INJURED?")]), existing)
        assert out == []

    def test_duplicate_adds_deduped(self):
        out = sanitize_proposals(_raw([_add("Same thing?"), _add("Same thing?")]), [])
        assert len(out) == 1

    def test_edit_unknown_target_and_duplicate_target_dropped(self):
        existing = [_question(5, "Old prompt?")]
        edits = [
            {"question_id": 99, "updated": _add("x?"), "rationale": "r", "change_summary": "c"},
            {"question_id": 5, "updated": _add("New prompt?"), "rationale": "r",
             "change_summary": "c"},
            {"question_id": 5, "updated": _add("Another?"), "rationale": "r",
             "change_summary": "c"},
        ]
        out = sanitize_proposals(_raw(question_edits=edits), existing)
        assert [p["id"] for p in out] == ["edit-1"]
        assert out[0]["payload"]["prompt"] == "New prompt?"

    def test_noop_edit_dropped(self):
        existing = [
            _question(
                7,
                "Where?",
                QuestionType.single_choice,
                options=[("Store", "store"), ("Sidewalk", "sidewalk")],
            )
        ]
        edits = [
            {
                "question_id": 7,
                "updated": _add(
                    "Where?",
                    "single_choice",
                    options=[
                        {"label": "Store", "value": "store"},
                        {"label": "Sidewalk", "value": "sidewalk"},
                    ],
                ),
                "rationale": "r",
                "change_summary": "c",
            }
        ]
        assert sanitize_proposals(_raw(question_edits=edits), existing) == []

    def test_caps_enforced(self):
        adds = [_add(f"Question number {i}?") for i in range(20)]
        out = sanitize_proposals(_raw(adds), [])
        assert len(out) == 15


EDIT_APPEND_OPTION = {
    "type": "single_choice",
    "prompt": "Where did it happen?",
    "help_text": None,
    "is_required": True,
    "config": {},
    "options": [
        {"label": "Store", "value": "store"},
        {"label": "Sidewalk", "value": "sidewalk"},
        {"label": "Workplace", "value": "workplace"},
    ],
}


async def _seed_advice(admin_client, session_factory, monkeypatch, itid, question_id):
    """Generate an advice row with two adds (same slug after slugify) + one edit."""
    await seed_ai_settings(session_factory)
    reply = advice_reply(
        "Overview",
        new_questions=[
            _add("Medical bills so far?", "number", config={"min": 0}),
            _add("Medical bills so far!", "number", config={"min": 0}),
        ],
        question_edits=[
            {
                "question_id": question_id,
                "updated": EDIT_APPEND_OPTION,
                "rationale": "More venues",
                "change_summary": "Adds a Workplace option",
            }
        ],
    )

    async def _fake(*args, **kwargs):
        return reply

    monkeypatch.setattr("app.services.openrouter.chat_completion", _fake)
    created = (await admin_client.post(f"/api/admin/ai/injury-types/{itid}/advice")).json()
    assert [p["id"] for p in created["proposals"]] == ["add-1", "add-2", "edit-1"]
    return created


async def _first_question(admin_client, itid) -> dict:
    return (await admin_client.get(f"/api/admin/injury-types/{itid}/questions")).json()[0]


class TestApplyProposals:
    async def test_apply_creates_questions_and_edits_target(
        self, admin_client, session_factory, monkeypatch
    ):
        itid = await _injury_type_with_question(admin_client)
        target = await _first_question(admin_client, itid)
        await _seed_advice(admin_client, session_factory, monkeypatch, itid, target["id"])

        applied = (
            await admin_client.post(
                f"/api/admin/ai/injury-types/{itid}/advice/apply",
                json={"proposal_ids": ["add-1", "add-2", "edit-1"]},
            )
        ).json()
        assert all(p["applied"] for p in applied["proposals"])
        assert all(p["applied_at"] for p in applied["proposals"])

        questions = (
            await admin_client.get(f"/api/admin/injury-types/{itid}/questions")
        ).json()
        # Same base slug from both adds -> unique suffixed slugs, appended order.
        new = questions[1:]
        assert [q["slug"] for q in new] == ["medical-bills-so-far", "medical-bills-so-far-2"]
        assert [q["display_order"] for q in questions] == [0, 1, 2]
        assert all(q["page_group"] is None for q in new)
        assert new[0]["config"] == {"min": 0}
        created_ids = [p["created_question_id"] for p in applied["proposals"][:2]]
        assert created_ids == [q["id"] for q in new]

        # Edit applied with PUT semantics: options replaced, slug untouched.
        edited = questions[0]
        assert edited["slug"] == target["slug"]
        assert [o["value"] for o in edited["options"]] == ["store", "sidewalk", "workplace"]

        # Applied state survives a fresh GET.
        fetched = (await admin_client.get(f"/api/admin/ai/injury-types/{itid}/advice")).json()
        assert fetched == applied

    async def test_new_questions_appear_in_patient_wizard(
        self, admin_client, session_factory, monkeypatch
    ):
        itid = await _injury_type_with_question(admin_client)
        target = await _first_question(admin_client, itid)
        await _seed_advice(admin_client, session_factory, monkeypatch, itid, target["id"])
        await admin_client.post(
            f"/api/admin/ai/injury-types/{itid}/advice/apply",
            json={"proposal_ids": ["add-1", "add-2"]},
        )
        start = (
            await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
        ).json()
        assert start["total_pages"] == 3
        prompts = [q["prompt"] for page in start["pages"] for q in page["questions"]]
        assert prompts[-2:] == ["Medical bills so far?", "Medical bills so far!"]

    async def test_reapply_is_idempotent(self, admin_client, session_factory, monkeypatch):
        itid = await _injury_type_with_question(admin_client)
        target = await _first_question(admin_client, itid)
        await _seed_advice(admin_client, session_factory, monkeypatch, itid, target["id"])
        for _ in range(2):
            resp = await admin_client.post(
                f"/api/admin/ai/injury-types/{itid}/advice/apply",
                json={"proposal_ids": ["add-1"]},
            )
            assert resp.status_code == 200
        questions = (
            await admin_client.get(f"/api/admin/injury-types/{itid}/questions")
        ).json()
        assert len(questions) == 2

    async def test_unknown_proposal_id_applies_nothing(
        self, admin_client, session_factory, monkeypatch
    ):
        itid = await _injury_type_with_question(admin_client)
        target = await _first_question(admin_client, itid)
        await _seed_advice(admin_client, session_factory, monkeypatch, itid, target["id"])
        resp = await admin_client.post(
            f"/api/admin/ai/injury-types/{itid}/advice/apply",
            json={"proposal_ids": ["add-1", "add-99"]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_proposal"
        questions = (
            await admin_client.get(f"/api/admin/injury-types/{itid}/questions")
        ).json()
        assert len(questions) == 1

    async def test_stale_edit_rolls_back_whole_request(
        self, admin_client, session_factory, monkeypatch
    ):
        itid = await _injury_type_with_question(admin_client)
        target = await _first_question(admin_client, itid)
        await _seed_advice(admin_client, session_factory, monkeypatch, itid, target["id"])
        resp = await admin_client.delete(
            f"/api/admin/injury-types/{itid}/questions/{target['id']}"
        )
        assert resp.status_code == 204

        resp = await admin_client.post(
            f"/api/admin/ai/injury-types/{itid}/advice/apply",
            json={"proposal_ids": ["add-1", "edit-1"]},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "stale_proposal"
        questions = (
            await admin_client.get(f"/api/admin/injury-types/{itid}/questions")
        ).json()
        assert questions == []
        fetched = (await admin_client.get(f"/api/admin/ai/injury-types/{itid}/advice")).json()
        assert not any(p["applied"] for p in fetched["proposals"])

    async def test_apply_without_advice_404(self, admin_client):
        itid = await _injury_type_with_question(admin_client)
        resp = await admin_client.post(
            f"/api/admin/ai/injury-types/{itid}/advice/apply",
            json={"proposal_ids": ["add-1"]},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "no_advice"
