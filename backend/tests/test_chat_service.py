from collections.abc import Mapping, Sequence
from uuid import UUID

import pytest

from data_chat.data.catalog import MAX_QUERY_RESULT_ROWS
from data_chat.llm.openai_intent import ResultTooLargeError
from data_chat.schemas.chat import ChatMessageRequest, GeneratedAnswer
from data_chat.schemas.intent import IntentDecision
from data_chat.services.chat import (
    RESULT_TOO_LARGE_MESSAGE,
    ChatWorkflow,
    DEMO_DATA_NOTICE,
    DEMO_SOURCE_PUBLISHER,
    DataAccessError,
    InvalidAnswerError,
)


class FakeInterpreter:
    def __init__(self, decision: IntentDecision | Exception) -> None:
        self.decision = decision
        self.questions: list[str] = []

    def interpret(self, question: str, history=()) -> IntentDecision:
        self.questions.append(question)
        if isinstance(self.decision, Exception):
            raise self.decision
        return self.decision


class FakeRepository:
    def __init__(
        self,
        rows: Sequence[Mapping[str, object]] | Exception,
    ) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def execute(
        self,
        query_id: str,
        parameters: Mapping[str, object],
        *,
        max_rows: int,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append((query_id, dict(parameters), max_rows))
        if isinstance(self.rows, Exception):
            raise self.rows
        return self.rows


class FakeAnswerGenerator:
    def __init__(self, answer: GeneratedAnswer | Exception) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, Sequence[Mapping[str, object]]]] = []

    def generate(
        self,
        question: str,
        query_id: str,
        rows: Sequence[Mapping[str, object]],
    ) -> GeneratedAnswer:
        self.calls.append((question, query_id, rows))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _decision(**fields: object) -> IntentDecision:
    return IntentDecision.model_validate({"outcome": "query", **fields})


def _workflow(
    decision: IntentDecision | Exception,
    rows: Sequence[Mapping[str, object]] | Exception,
    answer: GeneratedAnswer | Exception,
) -> tuple[ChatWorkflow, FakeInterpreter, FakeRepository, FakeAnswerGenerator]:
    interpreter = FakeInterpreter(decision)
    repository = FakeRepository(rows)
    answer_generator = FakeAnswerGenerator(answer)
    return (
        ChatWorkflow(interpreter, repository, answer_generator),
        interpreter,
        repository,
        answer_generator,
    )


def test_supported_query_uses_catalog_parameters_and_official_sources() -> None:
    workflow, _, repository, answer_generator = _workflow(
        _decision(query_id="matches_for_team", team_name="Mexico"),
        [
            {
                "home_team": "Mexico",
                "source_url": "https://www.fifa.com/example/match",
            },
            {
                "home_team": "Mexico",
                "source_url": "https://www.fifa.com/example/match",
            },
            {"home_team": "Mexico", "source_url": "https://not-official.example"},
        ],
        GeneratedAnswer(status="answered", answer="The approved result says Mexico played."),
    )
    existing_conversation = UUID("b1d4876a-915b-432f-9c99-24f3a2a6fc4e")
    request = ChatMessageRequest(
        conversation_id=existing_conversation,
        message="Show Mexico's matches",
    )

    response = workflow.respond(request)

    assert response.status == "answered"
    assert response.conversation_id == existing_conversation
    assert response.message_id != existing_conversation
    assert response.answer == "The approved result says Mexico played."
    assert repository.calls == [
        ("matches_for_team", {"team_name": "Mexico"}, MAX_QUERY_RESULT_ROWS)
    ]
    assert len(response.sources) == 1
    assert [str(url) for url in response.sources[0].urls] == [
        "https://www.fifa.com/example/match"
    ]
    assert len(answer_generator.calls) == 1


def test_synthetic_demo_results_are_labeled_and_never_linked_as_official() -> None:
    workflow, _, _, _ = _workflow(
        _decision(query_id="tournament_teams"),
        [
            {
                "team_name": "Demo Aurora FC",
                "source_publisher": DEMO_SOURCE_PUBLISHER,
                "source_url": "https://example.invalid/demo",
            }
        ],
        GeneratedAnswer(status="answered", answer="Demo Aurora FC is in group DEMO-A."),
    )

    response = workflow.respond(ChatMessageRequest(message="List the teams"))

    assert response.answer == (
        f"{DEMO_DATA_NOTICE}Demo Aurora FC is in group DEMO-A."
    )
    assert response.sources[0].label == (
        "Synthetic demo data - not official FIFA information"
    )
    assert response.sources[0].urls == []


def test_oversized_result_asks_user_to_narrow_the_question() -> None:
    workflow, _, _, _ = _workflow(
        _decision(query_id="matches_by_stage", stage_name="Demo Group Stage"),
        [{"home_team": "A", "source_publisher": DEMO_SOURCE_PUBLISHER}],
        ResultTooLargeError("too large"),
    )

    response = workflow.respond(ChatMessageRequest(message="All group matches"))

    assert response.status == "clarification_required"
    assert response.answer == RESULT_TOO_LARGE_MESSAGE
    assert response.sources == []


def test_answer_over_length_limit_after_demo_notice_asks_to_narrow() -> None:
    workflow, _, _, _ = _workflow(
        _decision(query_id="matches_by_stage", stage_name="Demo Group Stage"),
        [{"home_team": "A", "source_publisher": DEMO_SOURCE_PUBLISHER}],
        GeneratedAnswer(status="answered", answer="x" * 1990),
    )

    response = workflow.respond(ChatMessageRequest(message="All group matches"))

    assert response.status == "clarification_required"
    assert response.answer == RESULT_TOO_LARGE_MESSAGE


def test_mixed_demo_and_non_demo_results_are_rejected() -> None:
    workflow, _, _, answer_generator = _workflow(
        _decision(query_id="venues"),
        [
            {"venue_name": "Demo venue", "source_publisher": DEMO_SOURCE_PUBLISHER},
            {"venue_name": "Official venue", "source_publisher": "FIFA"},
        ],
        GeneratedAnswer(status="answered", answer="not used"),
    )

    with pytest.raises(DataAccessError, match="mixed demo"):
        workflow.respond(ChatMessageRequest(message="List venues"))

    assert answer_generator.calls == []


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (
            IntentDecision(outcome="unsupported"),
            "unsupported",
        ),
        (
            IntentDecision(
                outcome="clarification_required",
                clarification_question="Which team do you mean?",
            ),
            "clarification_required",
        ),
    ],
)
def test_non_query_decisions_do_not_access_data_or_answer_model(
    decision: IntentDecision,
    expected_status: str,
) -> None:
    workflow, _, repository, answer_generator = _workflow(
        decision,
        [],
        GeneratedAnswer(status="answered", answer="not used"),
    )

    response = workflow.respond(ChatMessageRequest(message="unsupported question"))

    assert response.status == expected_status
    assert repository.calls == []
    assert answer_generator.calls == []


def test_empty_query_results_return_insufficient_without_answer_model() -> None:
    workflow, _, repository, answer_generator = _workflow(
        _decision(query_id="group_standings", group_code="A"),
        [],
        GeneratedAnswer(status="answered", answer="not used"),
    )

    response = workflow.respond(ChatMessageRequest(message="Show group A"))

    assert response.status == "insufficient_data"
    assert response.answer == "No matching records were found in the approved data."
    assert response.sources[0].query_id == "group_standings"
    assert repository.calls
    assert answer_generator.calls == []


def test_answer_model_can_report_insufficient_fields_in_nonempty_data() -> None:
    workflow, _, _, answer_generator = _workflow(
        _decision(query_id="venues"),
        [{"venue_name": "Official venue"}],
        GeneratedAnswer(
            status="insufficient_data",
            answer="The available records do not include a kickoff time.",
        ),
    )

    response = workflow.respond(ChatMessageRequest(message="When is kickoff?"))

    assert response.status == "insufficient_data"
    assert response.answer == "The available records do not include a kickoff time."
    assert len(answer_generator.calls) == 1


def test_data_failure_is_not_converted_to_an_answer() -> None:
    workflow, _, _, answer_generator = _workflow(
        _decision(query_id="venues"),
        DataAccessError("internal database detail"),
        GeneratedAnswer(status="answered", answer="not used"),
    )

    with pytest.raises(DataAccessError):
        workflow.respond(ChatMessageRequest(message="List venues"))

    assert answer_generator.calls == []


def test_invalid_intent_stops_before_repository() -> None:
    from data_chat.llm.openai_intent import InvalidLLMOutputError

    workflow, _, repository, answer_generator = _workflow(
        InvalidLLMOutputError("invalid model output"),
        [],
        GeneratedAnswer(status="answered", answer="not used"),
    )

    with pytest.raises(InvalidLLMOutputError):
        workflow.respond(ChatMessageRequest(message="List teams"))

    assert repository.calls == []
    assert answer_generator.calls == []


def test_repository_cannot_exceed_the_configured_row_cap() -> None:
    rows = [
        {"venue_name": f"Venue {index}"}
        for index in range(MAX_QUERY_RESULT_ROWS + 1)
    ]
    workflow, _, _, answer_generator = _workflow(
        _decision(query_id="venues"),
        rows,
        GeneratedAnswer(status="answered", answer="not used"),
    )

    with pytest.raises(DataAccessError, match="result limit"):
        workflow.respond(ChatMessageRequest(message="List venues"))

    assert answer_generator.calls == []


def test_invalid_answer_is_rejected_before_api_response() -> None:
    workflow, _, _, _ = _workflow(
        _decision(query_id="venues"),
        [{"venue_name": "Official venue"}],
        InvalidAnswerError("invalid"),
    )

    with pytest.raises(InvalidAnswerError):
        workflow.respond(ChatMessageRequest(message="List venues"))


def test_new_conversation_id_is_created_without_claiming_persistence() -> None:
    workflow, _, _, _ = _workflow(
        IntentDecision(outcome="unsupported"),
        [],
        GeneratedAnswer(status="answered", answer="not used"),
    )

    response = workflow.respond(ChatMessageRequest(message="Hello"))

    assert isinstance(response.conversation_id, UUID)
    assert isinstance(response.message_id, UUID)


def test_follow_up_receives_prior_turns_and_stores_new_turn() -> None:
    from data_chat.services.conversations import ConversationStore, ConversationTurn

    class RecordingInterpreter(FakeInterpreter):
        def __init__(self, decisions: list[IntentDecision]) -> None:
            super().__init__(decisions[0])
            self.decisions = decisions
            self.histories: list[tuple[ConversationTurn, ...]] = []

        def interpret(self, question: str, history=()) -> IntentDecision:
            self.histories.append(tuple(history))
            return self.decisions.pop(0)

    clarification = IntentDecision.model_validate(
        {"outcome": "clarification_required", "clarification_question": "Which group?"}
    )
    interpreter = RecordingInterpreter(
        [clarification, _decision(query_id="group_standings", group_code="DEMO-B")]
    )
    workflow = ChatWorkflow(
        interpreter,
        FakeRepository([{"team": "B1", "source_url": "https://www.fifa.com/x"}]),
        FakeAnswerGenerator(GeneratedAnswer(status="answered", answer="B1 leads.")),
        ConversationStore(),
    )
    conversation_id = UUID("b1d4876a-915b-432f-9c99-24f3a2a6fc4e")

    first = workflow.respond(
        ChatMessageRequest(conversation_id=conversation_id, message="Show standings")
    )
    second = workflow.respond(
        ChatMessageRequest(conversation_id=conversation_id, message="DEMO-B")
    )

    assert interpreter.histories[0] == ()
    assert interpreter.histories[1] == (
        ConversationTurn("Show standings", first.answer),
    )
    assert second.status == "answered"
