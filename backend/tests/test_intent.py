from unittest.mock import Mock

import pytest
from openai import APIError, OpenAI
from pydantic import ValidationError

from data_chat.core.config import Settings
from data_chat.llm.openai_intent import (
    INTENT_INSTRUCTIONS,
    InvalidLLMOutputError,
    OpenAIConfigurationError,
    OpenAIIntentInterpreter,
    OpenAIProviderError,
    create_openai_client,
)
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


def test_interpreter_uses_structured_output_without_database_access() -> None:
    decision = IntentDecision.model_validate(
        {
            "outcome": "query",
            "query_id": "group_standings",
            "group_code": "A",
        }
    )
    client = Mock(spec=OpenAI)
    client.responses.parse.return_value.output_parsed = decision
    interpreter = OpenAIIntentInterpreter(client, "approved-model-id")

    result = interpreter.interpret("Show the final table for group A")

    assert result == decision
    call = client.responses.parse.call_args.kwargs
    assert call["model"] == "approved-model-id"
    assert call["text_format"] is IntentDecision
    assert call["instructions"] == INTENT_INSTRUCTIONS
    assert call["input"] == "Show the final table for group A"


def test_interpreter_requests_clarification_for_missing_group_code() -> None:
    decision = IntentDecision.model_validate(
        {
            "outcome": "clarification_required",
            "clarification_question": "Which group do you mean?",
        }
    )
    client = Mock(spec=OpenAI)
    client.responses.parse.return_value.output_parsed = decision
    interpreter = OpenAIIntentInterpreter(client, "approved-model-id")

    result = interpreter.interpret("Show the group standings")

    assert result == decision
    instructions = client.responses.parse.call_args.kwargs["instructions"]
    assert '"Show the group standings" has no group_code' in instructions
    assert 'may select group_standings with group_code "A"' in instructions


def test_interpreter_rejects_missing_structured_output() -> None:
    client = Mock(spec=OpenAI)
    client.responses.parse.return_value.output_parsed = None
    interpreter = OpenAIIntentInterpreter(client, "approved-model-id")

    with pytest.raises(InvalidLLMOutputError):
        interpreter.interpret("Show the standings")


def test_interpreter_maps_sdk_validation_errors() -> None:
    client = Mock(spec=OpenAI)
    with pytest.raises(ValidationError) as validation_error:
        IntentDecision.model_validate({"outcome": "query"})
    client.responses.parse.side_effect = validation_error.value
    interpreter = OpenAIIntentInterpreter(client, "approved-model-id")

    with pytest.raises(InvalidLLMOutputError):
        interpreter.interpret("Show the standings")


def test_interpreter_maps_openai_errors_without_exposing_provider_details() -> None:
    class StubAPIError(APIError):
        def __init__(self) -> None:
            Exception.__init__(self, "sensitive provider details")

    client = Mock(spec=OpenAI)
    client.responses.parse.side_effect = StubAPIError()
    interpreter = OpenAIIntentInterpreter(client, "approved-model-id")

    with pytest.raises(OpenAIProviderError) as exc_info:
        interpreter.interpret("Show the standings")

    assert "sensitive provider details" not in str(exc_info.value)


def test_interpreter_rejects_empty_and_oversized_questions() -> None:
    client = Mock(spec=OpenAI)
    interpreter = OpenAIIntentInterpreter(client, "approved-model-id")

    with pytest.raises(ValueError, match="empty"):
        interpreter.interpret("   ")
    with pytest.raises(ValueError, match="2000"):
        interpreter.interpret("x" * 2001)

    client.responses.parse.assert_not_called()


def test_openai_client_requires_credentials_and_model_without_requesting_api() -> None:
    settings = Settings.model_validate({})

    with pytest.raises(OpenAIConfigurationError):
        create_openai_client(settings)

    settings_with_key = Settings.model_validate({"openai_api_key": "test-key"})
    with pytest.raises(OpenAIConfigurationError):
        create_openai_client(settings_with_key)


def test_openai_client_can_be_configured_without_making_a_request() -> None:
    settings = Settings.model_validate(
        {
            "openai_api_key": "test-key",
            "openai_model": "approved-model-id",
        }
    )

    client = create_openai_client(settings)
    assert client.api_key == "test-key"
    client.close()
