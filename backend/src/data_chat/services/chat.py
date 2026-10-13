from collections.abc import Mapping, Sequence
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import HttpUrl, TypeAdapter

from data_chat.data.catalog import AUTHORIZED_QUERIES, MAX_QUERY_RESULT_ROWS
from data_chat.llm.openai_intent import InvalidLLMOutputError, ResultTooLargeError
from data_chat.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSource,
    GeneratedAnswer,
)
from data_chat.schemas.intent import IntentDecision

MAX_ANSWER_LENGTH = 2000
RESULT_TOO_LARGE_MESSAGE = (
    "That question matches too many records to summarize. Please narrow it, "
    "for example by asking about one team, venue, group or stage."
)
DEMO_SOURCE_PUBLISHER = "Synthetic demo data"
DEMO_DATA_NOTICE = "DEMO DATA ONLY - synthetic examples; not official FIFA facts. "
SOURCE_LABELS = {
    "tournament_teams": "Official participating teams and groups",
    "venues": "Official tournament venue information",
    "matches_for_team": "Official match schedule and results",
    "matches_at_venue": "Official match schedule and results",
    "matches_by_stage": "Official match schedule and results",
    "group_standings": "Official group standings",
    "team_final_placement": "Official final placement",
}
OFFICIAL_SOURCE_DOMAINS = ("fifa.com", "fifatrainingcentre.com")
MAX_SOURCE_URLS = 20
HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


class IntentInterpreter(Protocol):
    def interpret(self, question: str) -> IntentDecision: ...


class QueryRepository(Protocol):
    def execute(
        self,
        query_id: str,
        parameters: Mapping[str, object],
        *,
        max_rows: int,
    ) -> Sequence[Mapping[str, object]]: ...


class AnswerGenerator(Protocol):
    def generate(
        self,
        question: str,
        query_id: str,
        rows: Sequence[Mapping[str, object]],
    ) -> GeneratedAnswer: ...


class DataAccessUnavailable(RuntimeError):
    pass


class DataAccessError(RuntimeError):
    pass


class QueryTimeoutError(DataAccessError):
    pass


class InvalidAnswerError(RuntimeError):
    pass


class ChatWorkflow:
    def __init__(
        self,
        interpreter: IntentInterpreter,
        repository: QueryRepository,
        answer_generator: AnswerGenerator,
    ) -> None:
        self._interpreter = interpreter
        self._repository = repository
        self._answer_generator = answer_generator

    def respond(self, request: ChatMessageRequest) -> ChatMessageResponse:
        conversation_id = request.conversation_id or uuid4()
        message_id = uuid4()

        decision = self._interpreter.interpret(request.message)
        if decision.outcome == "clarification_required":
            return ChatMessageResponse(
                conversation_id=conversation_id,
                message_id=message_id,
                answer=decision.clarification_question or "",
                status="clarification_required",
            )
        if decision.outcome == "unsupported":
            return ChatMessageResponse(
                conversation_id=conversation_id,
                message_id=message_id,
                answer=(
                    "I can answer questions only about the supported "
                    "FIFA World Cup 2026 data."
                ),
                status="unsupported",
            )

        if decision.query_id is None:
            raise InvalidLLMOutputError(
                "The intent decision did not select an authorized query."
            )
        query_parameters = decision.validated_query_parameters()
        if decision.query_id not in AUTHORIZED_QUERIES:
            raise InvalidLLMOutputError(
                "The intent decision selected an unsupported query."
            )

        rows = list(
            self._repository.execute(
                decision.query_id,
                query_parameters,
                max_rows=MAX_QUERY_RESULT_ROWS,
            )
        )
        if len(rows) > MAX_QUERY_RESULT_ROWS:
            raise DataAccessError("The data service exceeded its result limit.")
        is_demo_data = _is_demo_data(rows)
        sources = _sources_for_rows(
            decision.query_id,
            rows,
            is_demo_data=is_demo_data,
        )
        if not rows:
            answer = "No matching records were found in the approved data."
            if is_demo_data:
                answer = f"{DEMO_DATA_NOTICE}{answer}"
            return ChatMessageResponse(
                conversation_id=conversation_id,
                message_id=message_id,
                answer=answer,
                status="insufficient_data",
                sources=sources,
            )

        try:
            generated_answer = self._answer_generator.generate(
                request.message,
                decision.query_id,
                rows,
            )
        except ResultTooLargeError:
            return _too_large_response(conversation_id, message_id)
        normalized_answer = generated_answer.answer.strip()
        if not normalized_answer:
            raise InvalidAnswerError("The answer service returned an invalid answer.")
        if len(normalized_answer) > MAX_ANSWER_LENGTH:
            return _too_large_response(conversation_id, message_id)
        if is_demo_data:
            normalized_answer = f"{DEMO_DATA_NOTICE}{normalized_answer}"
        if len(normalized_answer) > MAX_ANSWER_LENGTH:
            return _too_large_response(conversation_id, message_id)

        return ChatMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id,
            answer=normalized_answer,
            status=generated_answer.status,
            sources=sources,
        )


def _too_large_response(conversation_id: UUID, message_id: UUID) -> ChatMessageResponse:
    return ChatMessageResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        answer=RESULT_TOO_LARGE_MESSAGE,
        status="clarification_required",
    )


def _sources_for_rows(
    query_id: str,
    rows: Sequence[Mapping[str, object]],
    *,
    is_demo_data: bool = False,
) -> list[ChatSource]:
    if not rows:
        return [
            ChatSource(
                query_id=query_id,
                label="No records returned from the approved data source",
            )
        ]

    label = (
        "Synthetic demo data - not official FIFA information"
        if is_demo_data
        else SOURCE_LABELS[query_id]
    )
    urls: list[HttpUrl] = []
    if not is_demo_data:
        for row in rows:
            source_url = row.get("source_url")
            if not isinstance(source_url, str):
                continue
            normalized_url = source_url.strip()
            if normalized_url and _is_official_source_url(normalized_url):
                validated_url = HTTP_URL_ADAPTER.validate_python(normalized_url)
                if validated_url not in urls:
                    urls.append(validated_url)
                    if len(urls) == MAX_SOURCE_URLS:
                        break

    if not urls:
        return [ChatSource(query_id=query_id, label=label)]
    return [ChatSource(query_id=query_id, label=label, urls=urls)]


def _is_demo_data(rows: Sequence[Mapping[str, object]]) -> bool:
    publishers = {
        publisher
        for row in rows
        if isinstance((publisher := row.get("source_publisher")), str)
    }
    is_demo_data = DEMO_SOURCE_PUBLISHER in publishers
    if is_demo_data and publishers != {DEMO_SOURCE_PUBLISHER}:
        raise DataAccessError("A query returned mixed demo and non-demo data.")
    return is_demo_data


def _is_official_source_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return False
    if (
        parts.scheme != "https"
        or not hostname
        or "@" in parts.netloc
        or port not in (None, 443)
    ):
        return False
    hostname = hostname.lower().rstrip(".")
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in OFFICIAL_SOURCE_DOMAINS
    )
