AI_PAYLOAD = {
    "openrouter_api_key": "sk-or-secret-key",
    "openrouter_model": "anthropic/claude-sonnet-4.5",
}


async def test_ai_settings_roundtrip_masks_key(admin_client):
    initial = (await admin_client.get("/api/admin/settings")).json()
    assert initial["openrouter_api_key_set"] is False
    assert initial["openrouter_model"] is None

    saved = (await admin_client.put("/api/admin/settings", json=AI_PAYLOAD)).json()
    assert saved["openrouter_api_key_set"] is True
    assert saved["openrouter_model"] == "anthropic/claude-sonnet-4.5"
    assert "openrouter_api_key" not in saved

    fetched = (await admin_client.get("/api/admin/settings")).json()
    assert fetched == saved


async def test_pipeline_settings_roundtrip_and_defaults(admin_client):
    initial = (await admin_client.get("/api/admin/settings")).json()
    assert initial["comps_enabled"] is False
    assert initial["comps_model"] is None
    assert initial["sample_count"] == 5
    assert initial["contingency_fee_pct"] == 33.3

    payload = dict(
        AI_PAYLOAD,
        comps_enabled=True,
        comps_model="perplexity/sonar",
        sample_count=7,
        contingency_fee_pct=40,
    )
    saved = (await admin_client.put("/api/admin/settings", json=payload)).json()
    assert saved["comps_enabled"] is True
    assert saved["comps_model"] == "perplexity/sonar"
    assert saved["sample_count"] == 7
    assert saved["contingency_fee_pct"] == 40


async def test_pipeline_settings_validation(admin_client):
    for bad in (
        {"sample_count": 0},
        {"sample_count": 10},
        {"contingency_fee_pct": 5},
        {"contingency_fee_pct": 60},
    ):
        resp = await admin_client.put("/api/admin/settings", json=dict(AI_PAYLOAD, **bad))
        assert resp.status_code == 422, bad


async def test_omitted_key_kept_blank_key_clears(admin_client, session_factory):
    from app.services.email import get_app_settings

    await admin_client.put("/api/admin/settings", json=AI_PAYLOAD)

    keep = dict(AI_PAYLOAD, openrouter_api_key=None)
    kept = (await admin_client.put("/api/admin/settings", json=keep)).json()
    assert kept["openrouter_api_key_set"] is True
    async with session_factory() as s:
        row = await get_app_settings(s)
        assert row.openrouter_api_key == "sk-or-secret-key"

    clear = dict(AI_PAYLOAD, openrouter_api_key="")
    cleared = (await admin_client.put("/api/admin/settings", json=clear)).json()
    assert cleared["openrouter_api_key_set"] is False
