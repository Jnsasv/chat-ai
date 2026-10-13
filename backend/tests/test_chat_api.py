from collections.abc import Mapping, Sequence
from collections.abc import Generator
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import data_chat.main as main
from data_chat.main import app
from data_chat.llm.openai_intent import (
    InvalidLLMOutputError,
    OpenAIProviderError,
)
from data_chat.schemas.chat import GeneratedAnswer
from data_chat.schemas.intent import IntentDecision
from data_chat.services.chat import (
    ChatWorkflow,
    DataAccessError,
    QueryTimeoutError,
)


class ApiInterpreter:
    def interpret(self, question: str) -> IntentDecision:
        assert question
        return IntentDecision(outcome="unsupported")


class ApiRepository:
    def execute(
        self,
        query_id: str,
        parameters: Mapping[str, object],
        *,
        max_rows: int,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError((query_id, parameters, max_rows))


class ApiAnswerGenerator:
    def generate(
        self,
        question: str,
        query_id: str,
        rows: Sequence[Mapping[str, object]],
    ) -> GeneratedAnswer:
        raise AssertionError((question, query_id, rows))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("OPENAI_API_KEY", "replace-with-your-key")
    monkeypatch.setenv("OPENAI_MODEL", "replace-with-approved-model")
    monkeypatch.setenv(
        "SQL_SERVER_ODBC_CONNECTION_STRING",
        "replace-with-local-odbc-connection-string",
    )
    with TestClient(app) as test_client:
        yield test_client
    app.state.chat_workflow = None


def test_lifespan_wires_configured_workflow_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv(
        "SQL_SERVER_ODBC_CONNECTION_STRING",
        "Driver={ODBC Driver 17 for SQL Server};Server=localhost;"
        "Database=WorldCup2026Dev;Trusted_Connection=yes;"
        "Encrypt=yes;TrustServerCertificate=no;",
    )
    openai_client = Mock()
    engine = Mock()
    create_openai_client = Mock(return_value=openai_client)
    create_sql_server_engine = Mock(return_value=engine)
    monkeypatch.setattr(main, "create_openai_client", create_openai_client)
    monkeypatch.setattr(main, "create_sql_server_engine", create_sql_server_engine)

    with TestClient(app):
        assert isinstance(app.state.chat_workflow, ChatWorkflow)
        create_openai_client.assert_called_once()
        create_sql_server_engine.assert_called_once()
        openai_client.responses.parse.assert_not_called()
        engine.connect.assert_not_called()

    assert app.state.chat_workflow is None
    engine.dispose.assert_called_once()
    openai_client.close.assert_called_once()


def test_post_chat_returns_safe_unavailable_error_when_unconfigured(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        json={"message": "List teams"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "service_unavailable",
        "message": "Chat processing is not available right now.",
    }


def test_invalid_request_does_not_echo_user_input(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        json={"message": "secret-injection-payload", "sql": "DELETE"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": "request_invalid",
        "message": "The request does not match the required API contract.",
    }
    assert "secret-injection-payload" not in response.text


def test_chat_endpoint_returns_response_contract_for_injected_workflow(
    client: TestClient,
) -> None:
    app.state.chat_workflow = ChatWorkflow(
        ApiInterpreter(),
        ApiRepository(),
        ApiAnswerGenerator(),
    )

    response = client.post(
        "/api/v1/chat/messages",
        json={
            "conversation_id": "b1d4876a-915b-432f-9c99-24f3a2a6fc4e",
            "message": "Tell me about a different subject",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "b1d4876a-915b-432f-9c99-24f3a2a6fc4e"
    assert UUID(body["message_id"])
    assert body["status"] == "unsupported"
    assert body["sources"] == []


def test_chat_contract_appears_in_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/chat/messages"]["post"]
    assert operation["requestBody"]
    assert "200" in operation["responses"]
    assert "422" in operation["responses"]
    assert "503" in operation["responses"]


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_category"),
    [
        (OpenAIProviderError("sensitive provider details"), 503, "upstream_error"),
        (InvalidLLMOutputError("sensitive model output"), 502, "upstream_invalid_response"),
        (DataAccessError("sensitive database details"), 502, "upstream_error"),
        (QueryTimeoutError("sensitive timeout details"), 504, "upstream_error"),
    ],
)
def test_upstream_failure_uses_safe_error_envelope(
    client: TestClient,
    failure: Exception,
    expected_status: int,
    expected_category: str,
) -> None:
    class FailingInterpreter:
        def interpret(self, question: str) -> IntentDecision:
            assert question
            if isinstance(failure, (OpenAIProviderError, InvalidLLMOutputError)):
                raise failure
            return IntentDecision(outcome="query", query_id="venues")

    class FailingRepository:
        def execute(
            self,
            query_id: str,
            parameters: Mapping[str, object],
            *,
            max_rows: int,
        ) -> Sequence[Mapping[str, object]]:
            assert query_id == "venues"
            assert parameters == {}
            assert max_rows > 0
            raise failure

    app.state.chat_workflow = ChatWorkflow(
        FailingInterpreter(),
        FailingRepository(),
        ApiAnswerGenerator(),
    )

    response = client.post(
        "/api/v1/chat/messages",
        json={"message": "List teams"},
    )

    assert response.status_code == expected_status
    assert response.json()["error"] == expected_category
    assert str(failure) not in response.text
