import json

import pytest

from app.services.estimate_pipeline.adversarial import (
    describe_rule,
    parse_adversarial,
)
from app.services.estimate_pipeline.canonical import CanonicalExtraction
from app.services.estimate_pipeline.comps import (
    build_comps_messages,
    parse_comps,
    resolve_comps_model,
)
from app.services.estimate_pipeline.judgment import (
    JudgmentSample,
    aggregate_samples,
    build_judgment_messages,
    minimum_valid_samples,
    parse_judgment,
)


def sample(tier: int, pct: float) -> JudgmentSample:
    return JudgmentSample(severity_tier=tier, defendant_liability_pct=pct, swing_fact=f"s{tier}")


class TestJudgment:
    def test_aggregate_takes_medians_and_spreads(self):
        agg = aggregate_samples(
            [sample(2, 60), sample(3, 90), sample(3, 95), sample(4, 80), sample(3, 85)]
        )
        assert agg.median_tier == 3
        assert agg.median_liability_pct == 85
        assert agg.tier_spread == 2
        assert agg.liability_spread == 35
        assert len(agg.swing_facts) == 5

    def test_even_count_median_tier_rounds_half_up(self):
        agg = aggregate_samples([sample(2, 50), sample(3, 60)])
        assert agg.median_tier == 3  # median 2.5 → 3

    def test_aggregate_empty_raises(self):
        with pytest.raises(ValueError):
            aggregate_samples([])

    def test_minimum_valid_samples_is_majority(self):
        assert [minimum_valid_samples(n) for n in (1, 2, 5, 7)] == [1, 1, 3, 4]

    def test_parse_clamps_out_of_range_values(self):
        parsed = parse_judgment(
            json.dumps({"severity_tier": 9, "defendant_liability_pct": 140})
        )
        assert (parsed.severity_tier, parsed.defendant_liability_pct) == (5, 100.0)

    def test_messages_forbid_dollars_and_carry_extraction(self):
        x = CanonicalExtraction.model_validate({"meta": {"state": "TX"}})
        msgs = build_judgment_messages(x)
        assert "NEVER output a dollar amount" in msgs[0]["content"]
        assert '"state": "TX"' in msgs[1]["content"]


class TestAdversarial:
    def test_parse_builds_summary_and_trims_arguments(self):
        content = json.dumps(
            {
                "lowest_defensible_pct_of_specials": 75,
                "low_rationale": "Undocumented bills.",
                "attack_arguments": [
                    {"category": "documentation", "argument": "No bills provided."},
                    {"category": "causation", "argument": " Late treatment. "},
                    {"category": "credibility", "argument": ""},
                    {"category": "pre_existing", "argument": "Fourth argument dropped."},
                ],
            }
        )
        summary = parse_adversarial(content)
        assert summary.lowest_defensible_pct_of_specials == 75
        assert [a["argument"] for a in summary.attack_arguments] == [
            "No bills provided.",
            "Late treatment.",
        ]

    def test_pct_clamped(self):
        summary = parse_adversarial(
            json.dumps({"lowest_defensible_pct_of_specials": -20, "attack_arguments": []})
        )
        assert summary.lowest_defensible_pct_of_specials == 0.0

    def test_describe_rule(self):
        class Rule:
            state_name = "New York"
            comparative_rule = "pure"
            no_fault = True

        assert describe_rule(Rule()) == "New York: pure comparative negligence; no-fault/PIP state"
        assert describe_rule(None) is None


class TestComps:
    def test_resolve_comps_model(self):
        assert resolve_comps_model(None, "vendor/main") == "vendor/main:online"
        assert resolve_comps_model(None, "vendor/main:online") == "vendor/main:online"
        assert resolve_comps_model("perplexity/sonar", "vendor/main") == "perplexity/sonar"

    def test_parse_drops_junk_and_merges_annotation_urls(self):
        content = json.dumps(
            {
                "comps": [
                    {"amount": 50_000, "source_quality": "published_verdict",
                     "source_url": None, "description": "a", "injury_match": "b",
                     "venue": "c", "year": 2024, "kind": "verdict"},
                    {"amount": 0, "source_quality": "news", "source_url": None,
                     "description": "junk", "injury_match": "", "venue": "", "year": None,
                     "kind": "unknown"},
                    {"amount": 80_000, "source_quality": "invalid-tag",
                     "source_url": "https://firm.example/win", "description": "d",
                     "injury_match": "e", "venue": "f", "year": None, "kind": "bogus"},
                ]
            }
        )
        annotations = [
            {"type": "url_citation", "url_citation": {"url": "https://court.example/op"}}
        ]
        summary = parse_comps(content, annotations)
        assert len(summary.comps) == 2
        assert summary.comps[0]["source_url"] == "https://court.example/op"
        assert summary.comps[1]["source_quality"] == "firm_marketing"
        assert summary.comps[1]["kind"] == "unknown"

    def test_messages_target_venue_and_treatment(self):
        x = CanonicalExtraction.model_validate(
            {
                "meta": {"state": "CA", "county": "San Bernardino"},
                "injury": {
                    "body_parts": ["neck"],
                    "objective_finding": {"finding_verbatim": "cervical herniation"},
                    "treatment_ladder": {"highest_reached": "injections"},
                },
                "liability": {"mva": {"impact_type": "rear_ended"}},
            }
        )
        content = build_comps_messages(x, "Auto Accident")[1]["content"]
        assert "San Bernardino, CA" in content
        assert "cervical herniation" in content
        assert "injections" in content
        assert "rear ended" in content
