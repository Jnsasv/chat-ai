from unittest.mock import Mock

import pytest
from openai import OpenAI

from data_chat.llm.openai_answer import (
    MAX_ANSWER_INPUT_CHARS,
    OpenAIAnswerGenerator,
)
from data_chat.llm.openai_intent import (
    InvalidLLMOutputError,
    OpenAIProviderError,
    ResultTooLargeError,
)
from data_chat.schemas.chat import GeneratedAnswer


def test_answer_generator_uses_structured_data_only_prompt() -> None:
    expected = GeneratedAnswer(status="answered", answer="The provided result says 2.")
    client = Mock(spec=OpenAI)
    client.responses.parse.return_value.output_parsed = expected
    generator = OpenAIAnswerGenerator(client, "approved-model-id")

    result = generator.generate(
        "How many?",
        "group_standings",
        [{"points": 2, "source_url": "https://www.fifa.com/example"}],
    )

    assert result == expected
    call = client.responses.parse.call_args.kwargs
    assert call["model"] == "approved-model-id"
    assert call["text_format"] is GeneratedAnswer
    assert "Never add facts" in call["instructions"]
    assert "group_standings" in call["input"]
    assert "https://www.fifa.com/example" in call["input"]


def test_answer_generator_rejects_missing_parsed_answer() -> None:
    client = Mock(spec=OpenAI)
    client.responses.parse.return_value.output_parsed = None
    generator = OpenAIAnswerGenerator(client, "approved-model-id")

    with pytest.raises(InvalidLLMOutputError):
        generator.generate("Question", "venues", [{"venue_name": "A"}])


def test_answer_generator_rejects_oversized_result_before_api_call() -> None:
    client = Mock(spec=OpenAI)
    generator = OpenAIAnswerGenerator(client, "approved-model-id")
    large_row = {"data": "x" * MAX_ANSWER_INPUT_CHARS}

    with pytest.raises(ResultTooLargeError):
        generator.generate("Question", "venues", [large_row])

    client.responses.parse.assert_not_called()


def test_answer_generator_maps_provider_errors_safely() -> None:
    from openai import APIError

    class StubAPIError(APIError):
        def __init__(self) -> None:
            Exception.__init__(self, "sensitive detail")

    client = Mock(spec=OpenAI)
    client.responses.parse.side_effect = StubAPIError()
    generator = OpenAIAnswerGenerator(client, "approved-model-id")

    with pytest.raises(OpenAIProviderError) as exc_info:
        generator.generate("Question", "venues", [{"venue_name": "A"}])

    assert "sensitive detail" not in str(exc_info.value)
