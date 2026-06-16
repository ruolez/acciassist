from app.models import QuestionType
from app.services.summary import answer_display_value, render_template


class TestAnswerDisplayValue:
    def test_yes_no_true_renders_yes(self):
        assert answer_display_value(QuestionType.yes_no, True) == "Yes"

    def test_yes_no_false_renders_no(self):
        assert answer_display_value(QuestionType.yes_no, False) == "No"

    def test_single_choice_uses_option_label(self):
        result = answer_display_value(
            QuestionType.single_choice, "drv", {"drv": "Driver", "pax": "Passenger"}
        )
        assert result == "Driver"

    def test_multi_choice_joins_labels(self):
        result = answer_display_value(
            QuestionType.multi_choice, ["neck", "back"], {"neck": "Neck", "back": "Back"}
        )
        assert result == "Neck, Back"

    def test_short_text_passthrough(self):
        assert answer_display_value(QuestionType.short_text, "Acme St") == "Acme St"

    def test_none_renders_empty(self):
        assert answer_display_value(QuestionType.number, None) == ""


class TestRenderTemplate:
    def test_substitutes_known_tokens(self):
        body = "Hello {{ name }}, injured {{part}}."
        assert render_template(body, {"name": "Pat", "part": "neck"}) == "Hello Pat, injured neck."

    def test_unknown_token_becomes_empty(self):
        assert render_template("X={{ missing }}", {}) == "X="

    def test_no_tokens_returns_body_unchanged(self):
        assert render_template("plain text", {"a": "1"}) == "plain text"
