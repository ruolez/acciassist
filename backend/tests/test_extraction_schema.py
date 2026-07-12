import json

from app.services.estimate_pipeline.canonical import (
    EXTRACTION_JSON_SCHEMA,
    CanonicalExtraction,
)
from app.services.estimate_pipeline.extraction import (
    build_extraction_messages,
    parse_extraction,
)


def _walk_objects(schema: object, path: str = "$"):
    """Yield (path, schema) for every object-typed schema node."""
    if isinstance(schema, dict):
        node_type = schema.get("type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "object" in types:
            yield path, schema
        for key in ("properties",):
            for name, sub in (schema.get(key) or {}).items():
                yield from _walk_objects(sub, f"{path}.{name}")
        if "items" in schema:
            yield from _walk_objects(schema["items"], f"{path}[]")


class TestStrictModeInvariants:
    """OpenRouter strict structured output requires every object to list all
    of its keys in `required` and forbid additional properties. A violation
    silently downgrades routing, so it is locked in by test."""

    def test_every_object_requires_all_keys(self):
        for path, node in _walk_objects(EXTRACTION_JSON_SCHEMA):
            props = list(node.get("properties", {}))
            assert node.get("required") == props, f"{path}: required != all keys"

    def test_every_object_forbids_additional_properties(self):
        for path, node in _walk_objects(EXTRACTION_JSON_SCHEMA):
            assert node.get("additionalProperties") is False, path

    def test_schema_is_json_serializable_with_null_enums(self):
        text = json.dumps(EXTRACTION_JSON_SCHEMA)
        assert '"enum"' in text and "null" in text


class TestCanonicalModel:
    def test_empty_object_yields_all_nulls(self):
        x = CanonicalExtraction.model_validate({})
        assert x.meta.state is None
        assert x.economic.medical_billed_to_date.amount is None
        assert x.economic.medical_billed_to_date.documented is False
        assert x.liability.mva is None
        assert x.extraction_notes.model_refusals == []

    def test_state_names_normalize_to_codes(self):
        for raw, code in [("California", "CA"), ("ca", "CA"), ("district of columbia", "DC")]:
            assert CanonicalExtraction.model_validate({"meta": {"state": raw}}).meta.state == code

    def test_unknown_state_becomes_null(self):
        x = CanonicalExtraction.model_validate({"meta": {"state": "Ontario"}})
        assert x.meta.state is None

    def test_amounts_clamped_and_dates_tolerant(self):
        x = CanonicalExtraction.model_validate(
            {
                "meta": {"incident_date": "not a date"},
                "economic": {"medical_billed_to_date": {"amount": -500, "documented": True}},
            }
        )
        assert x.meta.incident_date is None
        assert x.economic.medical_billed_to_date.amount == 0.0
        assert x.economic.medical_billed_to_date.documented is True

    def test_enum_tokens_are_case_insensitive(self):
        x = CanonicalExtraction.model_validate(
            {
                "injury": {"treatment_ladder": {"highest_reached": "Surgery_Performed"}},
                "liability": {"mva": {"impact_type": "REAR_ENDED"}},
            }
        )
        assert x.injury.treatment_ladder.highest_reached == "surgery_performed"
        assert x.liability.mva.impact_type == "rear_ended"

    def test_parse_extraction_tolerates_fences_and_think_blocks(self):
        payload = {"meta": {"state": "TX"}, "gates": {"release_signed": False}}
        content = f"<think>{{scratch}}</think>\n```json\n{json.dumps(payload)}\n```"
        x = parse_extraction(content)
        assert x.meta.state == "TX"
        assert x.gates.release_signed is False


def test_extraction_messages_carry_slugs_and_injury_type():
    msgs = build_extraction_messages(
        "Auto Accident", [("state", "What state?", "Texas"), ("bills", "Bills?", "(not answered)")]
    )
    assert msgs[0]["role"] == "system"
    assert "- [state] What state?: Texas" in msgs[1]["content"]
    assert "Auto Accident" in msgs[1]["content"]
