
import pytest
from pydantic import ValidationError

from data_chat.schemas.intent import IntentDecision


def test_query_intent_validates_parameters_against_its_catalog_entry() -> None:
    decision = IntentDecision.model_validate(
        {
            "outcome": "query",
            "query_id": "matches_for_team",
            "team_name": "Mexico",
        }
    )

    assert decision.validated_query_parameters() == {"team_name": "Mexico"}


def test_query_intent_rejects_parameters_for_another_query() -> None:
    with pytest.raises(ValidationError):
        IntentDecision.model_validate(
            {
                "outcome": "query",
                "query_id": "matches_for_team",
                "team_name": "Mexico",
                "group_code": "A",
            }
        )


def test_query_intent_rejects_unknown_query_ids_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        IntentDecision.model_validate(
            {"outcome": "query", "query_id": "SELECT 1"}
        )

    with pytest.raises(ValidationError):
        IntentDecision.model_validate(
            {
                "outcome": "query",
                "query_id": "venues",
                "sql": "SELECT * FROM wc2026.Team",
            }
        )


def test_non_query_decision_cannot_include_a_query_or_parameters() -> None:
    with pytest.raises(ValidationError):
        IntentDecision.model_validate(
            {
                "outcome": "unsupported",
                "query_id": "venues",
            }
        )


def test_clarification_decision_requires_a_question() -> None:
    with pytest.raises(ValidationError):
        IntentDecision.model_validate({"outcome": "clarification_required"})


def test_clarification_decision_accepts_only_a_bounded_question() -> None:
    decision = IntentDecision.model_validate(
        {
            "outcome": "clarification_required",
            "clarification_question": "Which team do you mean?",
        }
    )

    assert decision.clarification_question == "Which team do you mean?"


def test_unsupported_decision_is_valid_without_query_parameters() -> None:
    decision = IntentDecision.model_validate({"outcome": "unsupported"})

    assert decision.outcome == "unsupported"
