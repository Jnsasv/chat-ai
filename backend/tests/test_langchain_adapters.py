from unittest.mock import Mock

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from openai import APIError
from pydantic import ValidationError

from data_chat.core.config import Settings
from data_chat.llm.langchain_adapters import (
    HISTORY_INSTRUCTIONS,
    LangChainAnswerGenerator,
    LangChainIntentInterpreter,
    create_chat_model,
)
from data_chat.llm.openai_answer import ANSWER_INSTRUCTIONS, MAX_ANSWER_INPUT_CHARS
from data_chat.llm.openai_intent import (
    INTENT_INSTRUCTIONS,
    InvalidLLMOutputError,
    OpenAIConfigurationError,
    OpenAIProviderError,
    ResultTooLargeError,
)
from data_chat.schemas.chat import GeneratedAnswer
from data_chat.schemas.intent import IntentDecision
from data_chat.services.conversations import ConversationTurn


def _model(result: object = None, error: Exception | None = None) -> tuple[Mock, Mock]:
    model = Mock(spec=BaseChatModel)
    structured = Mock()
    if error is not None:
        structured.invoke.side_effect = error
    else:
        structured.invoke.return_value = result
    model.with_structured_output.return_value = structured
    return model, structured


def _standings_decision() -> IntentDecision:
    return IntentDecision.model_validate(
        {"outcome": "query", "query_id": "group_standings", "group_code": "A"}
    )


class StubAPIError(APIError):
    def __init__(self) -> None:
        Exception.__init__(self, "sensitive provider details")


def test_intent_interpreter_requests_schema_constrained_output() -> None:
    decision = _standings_decision()
    model, structured = _model(decision)
    interpreter = LangChainIntentInterpreter(model)

    result = interpreter.interpret("Show the final table for group A")

    assert result == decision
    args, kwargs = model.with_structured_output.call_args
    assert args == (IntentDecision,)
    assert kwargs == {"method": "json_schema"}
    messages = structured.invoke.call_args.args[0]
    assert messages == [
        SystemMessage(INTENT_INSTRUCTIONS),
        HumanMessage("Show the final table for group A"),
    ]


def test_intent_interpreter_revalidates_dict_output() -> None:
    model, _ = _model(
        {"outcome": "query", "query_id": "group_standings", "group_code": "A"}
    )

    result = LangChainIntentInterpreter(model).interpret("Group A table")

    assert result == _standings_decision()


def test_intent_interpreter_sends_history_as_untrusted_context() -> None:
    model, structured = _model(_standings_decision())
    history = [ConversationTurn("Show the group standings", "Which group?")]

    LangChainIntentInterpreter(model).interpret("DEMO-B", history)

    messages = structured.invoke.call_args.args[0]
    assert messages == [
        SystemMessage(f"{INTENT_INSTRUCTIONS}\n\n{HISTORY_INSTRUCTIONS}"),
        HumanMessage("Show the group standings"),
        AIMessage("Which group?"),
        HumanMessage("DEMO-B"),
    ]
    assert "untrusted" in HISTORY_INSTRUCTIONS
    assert "assistant answer alone" in HISTORY_INSTRUCTIONS


def test_intent_interpreter_rejects_invalid_schema_output() -> None:
    model, _ = _model({"outcome": "query", "query_id": "SELECT 1"})

    with pytest.raises(InvalidLLMOutputError):
        LangChainIntentInterpreter(model).interpret("Show the standings")


@pytest.mark.parametrize(
    "error",
    [OutputParserException("bad json"), ValidationError.from_exception_data("x", [])],
)
def test_intent_interpreter_maps_output_errors(error: Exception) -> None:
    model, _ = _model(error=error)

    with pytest.raises(InvalidLLMOutputError):
        LangChainIntentInterpreter(model).interpret("Show the standings")


def test_intent_interpreter_rejects_missing_output() -> None:
    model, _ = _model(None)

    with pytest.raises(InvalidLLMOutputError):
        LangChainIntentInterpreter(model).interpret("Show the standings")


def test_intent_interpreter_hides_provider_details() -> None:
    model, _ = _model(error=StubAPIError())

    with pytest.raises(OpenAIProviderError) as exc_info:
        LangChainIntentInterpreter(model).interpret("Show the standings")

    assert "sensitive provider details" not in str(exc_info.value)


def test_intent_interpreter_rejects_empty_and_oversized_questions() -> None:
    model, structured = _model(_standings_decision())
    interpreter = LangChainIntentInterpreter(model)

    with pytest.raises(ValueError, match="empty"):
        interpreter.interpret("   ")
    with pytest.raises(ValueError, match="2000"):
        interpreter.interpret("x" * 2001)

    structured.invoke.assert_not_called()


def test_answer_generator_uses_structured_data_only_prompt() -> None:
    expected = GeneratedAnswer(status="answered", answer="The provided result says 2.")
    model, structured = _model(expected)

    result = LangChainAnswerGenerator(model).generate(
        "How many?",
        "group_standings",
        [{"points": 2, "source_url": "https://www.fifa.com/example"}],
    )

    assert result == expected
    assert model.with_structured_output.call_args.args == (GeneratedAnswer,)
    system, human = structured.invoke.call_args.args[0]
    assert system == SystemMessage(ANSWER_INSTRUCTIONS)
    assert "group_standings" in human.content
    assert "https://www.fifa.com/example" in human.content


def test_answer_generator_rejects_missing_output() -> None:
    model, _ = _model(None)

    with pytest.raises(InvalidLLMOutputError):
        LangChainAnswerGenerator(model).generate(
            "Question", "venues", [{"venue_name": "A"}]
        )


def test_answer_generator_rejects_oversized_result_before_model_call() -> None:
    model, structured = _model(GeneratedAnswer(status="answered", answer="x"))
    large_row = {"data": "x" * MAX_ANSWER_INPUT_CHARS}

    with pytest.raises(ResultTooLargeError):
        LangChainAnswerGenerator(model).generate("Question", "venues", [large_row])

    structured.invoke.assert_not_called()


def test_answer_generator_maps_provider_errors_safely() -> None:
    model, _ = _model(error=StubAPIError())

    with pytest.raises(OpenAIProviderError) as exc_info:
        LangChainAnswerGenerator(model).generate(
            "Question", "venues", [{"venue_name": "A"}]
        )

    assert "sensitive provider details" not in str(exc_info.value)


def test_chat_model_requires_credentials_and_model() -> None:
    with pytest.raises(OpenAIConfigurationError):
        create_chat_model(Settings.model_validate({}))

    with pytest.raises(OpenAIConfigurationError):
        create_chat_model(Settings.model_validate({"openai_api_key": "test-key"}))


def test_chat_model_is_configured_without_making_a_request() -> None:
    settings = Settings.model_validate(
        {"openai_api_key": "test-key", "openai_model": "approved-model-id"}
    )

    model = create_chat_model(settings)

    assert model.model_name == "approved-model-id"
