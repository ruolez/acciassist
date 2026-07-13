from app.models import QuestionType
from app.seed import _AUTO_QUESTIONS, _FALL_QUESTIONS

CHOICE_TYPES = (QuestionType.single_choice, QuestionType.multi_choice)


def _check(questions: list[tuple]) -> None:
    slugs = [q[0] for q in questions]
    assert len(slugs) == len(set(slugs)), "duplicate question slugs"
    for slug, qtype, prompt, _help, _required, _group, config, options in questions:
        assert prompt.strip()
        if qtype in CHOICE_TYPES:
            assert len(options) >= 2, f"{slug}: choice question needs 2+ options"
            values = [v for _, v in options]
            assert len(values) == len(set(values)), f"{slug}: duplicate option values"
        else:
            assert options == [], f"{slug}: non-choice question must not have options"
        if qtype is QuestionType.number:
            assert config.get("min") == 0, f"{slug}: dollar/number fields start at 0"


def test_auto_accident_questionnaire_is_structurally_valid():
    _check(_AUTO_QUESTIONS)
    slugs = {q[0] for q in _AUTO_QUESTIONS}
    # The high-signal fields the pipeline keys on.
    assert {
        "state_county", "incident_date", "release_signed", "impact_type",
        "objective_finding", "treatment_level", "treatment_gap_30d",
        "medical_bills_amount", "medical_bills_documented", "health_payor",
        "employment_type", "property_damage", "commercial_defendant",
    } <= slugs


def test_slip_and_fall_questionnaire_is_structurally_valid():
    _check(_FALL_QUESTIONS)
    slugs = {q[0] for q in _FALL_QUESTIONS}
    assert {
        "state_county", "incident_date", "release_signed", "location_type",
        "claimant_status", "hazard_duration", "warning_signs", "hazard_obvious",
        "incident_report_same_day", "surveillance", "medical_bills_amount",
    } <= slugs


def test_location_question_uses_composite_type():
    for questions in (_AUTO_QUESTIONS, _FALL_QUESTIONS):
        location = next(q for q in questions if q[0] == "state_county")
        assert location[1] is QuestionType.us_state_county
        assert location[4] is True  # required


def test_every_dollar_question_has_a_documented_pair():
    for questions in (_AUTO_QUESTIONS, _FALL_QUESTIONS):
        slugs = {q[0] for q in questions}
        assert "medical_bills_documented" in slugs
        assert "wages_documentable" in slugs
