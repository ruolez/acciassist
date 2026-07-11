async def _questionnaire(admin_client, count=4):
    resp = await admin_client.post(
        "/api/admin/injury-types", json={"name": "Auto Accident", "is_published": True}
    )
    itid = resp.json()["id"]
    ids = []
    for i in range(count):
        q = await admin_client.post(
            f"/api/admin/injury-types/{itid}/questions",
            json={"type": "short_text", "prompt": f"Question {i}?"},
        )
        assert q.status_code == 201
        ids.append(q.json()["id"])
    return itid, ids


async def _get_questions(admin_client, itid):
    return (await admin_client.get(f"/api/admin/injury-types/{itid}/questions")).json()


async def test_layout_round_trips_through_wizard_pages(admin_client):
    itid, (a, b, c, d) = await _questionnaire(admin_client)
    resp = await admin_client.put(
        f"/api/admin/injury-types/{itid}/questions/layout",
        json={"pages": [[a], [b, c], [d]]},
    )
    assert resp.status_code == 204

    questions = await _get_questions(admin_client, itid)
    assert [q["id"] for q in questions] == [a, b, c, d]
    assert [q["page_group"] for q in questions] == [None, 1, 1, None]

    start = (
        await admin_client.post("/api/intake/start", json={"injury_type_id": itid})
    ).json()
    assert [[q["id"] for q in p["questions"]] for p in start["pages"]] == [
        [a],
        [b, c],
        [d],
    ]


async def test_layout_reorders_across_pages(admin_client):
    itid, (a, b, c, d) = await _questionnaire(admin_client)
    resp = await admin_client.put(
        f"/api/admin/injury-types/{itid}/questions/layout",
        json={"pages": [[d, a], [c], [b]]},
    )
    assert resp.status_code == 204
    questions = await _get_questions(admin_client, itid)
    assert [q["id"] for q in questions] == [d, a, c, b]
    assert [q["page_group"] for q in questions] == [0, 0, None, None]


async def test_single_question_pages_always_get_null_group(admin_client):
    itid, ids = await _questionnaire(admin_client)
    resp = await admin_client.put(
        f"/api/admin/injury-types/{itid}/questions/layout",
        json={"pages": [[qid] for qid in ids]},
    )
    assert resp.status_code == 204
    questions = await _get_questions(admin_client, itid)
    assert [q["page_group"] for q in questions] == [None] * 4


async def test_layout_rejects_wrong_id_sets(admin_client):
    itid, (a, b, c, d) = await _questionnaire(admin_client)
    for pages in ([[a, b], [c]], [[a, b], [c, d], [9999]]):
        resp = await admin_client.put(
            f"/api/admin/injury-types/{itid}/questions/layout", json={"pages": pages}
        )
        assert resp.status_code == 400, pages
        assert resp.json()["error"]["code"] == "invalid_layout"


async def test_layout_rejects_duplicates_and_empty_pages(admin_client):
    itid, (a, b, c, d) = await _questionnaire(admin_client)
    for pages in ([[a, a], [b, c, d]], [[a, b], [], [c, d]]):
        resp = await admin_client.put(
            f"/api/admin/injury-types/{itid}/questions/layout", json={"pages": pages}
        )
        assert resp.status_code == 422, pages
        assert resp.json()["error"]["code"] == "validation_error"


async def test_stale_layout_after_delete_rejected(admin_client):
    itid, (a, b, c, d) = await _questionnaire(admin_client)
    await admin_client.delete(f"/api/admin/injury-types/{itid}/questions/{d}")
    resp = await admin_client.put(
        f"/api/admin/injury-types/{itid}/questions/layout",
        json={"pages": [[a], [b, c], [d]]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_layout"


async def test_question_update_preserves_page_group(admin_client):
    itid, (a, b, c, d) = await _questionnaire(admin_client)
    await admin_client.put(
        f"/api/admin/injury-types/{itid}/questions/layout",
        json={"pages": [[a], [b, c], [d]]},
    )
    resp = await admin_client.put(
        f"/api/admin/injury-types/{itid}/questions/{b}",
        json={"type": "short_text", "prompt": "Renamed question?"},
    )
    assert resp.status_code == 200
    assert resp.json()["page_group"] == 1


async def test_empty_layout_on_empty_questionnaire(admin_client):
    itid, _ = await _questionnaire(admin_client, count=0)
    resp = await admin_client.put(
        f"/api/admin/injury-types/{itid}/questions/layout", json={"pages": []}
    )
    assert resp.status_code == 204
