from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from starlette.requests import Request

from data_chat.api.chat import ChatServiceUnavailable, router as chat_router
from data_chat.api.health import router as health_router
from data_chat.core.config import Settings
from data_chat.core.logging import configure_logging
from data_chat.data.catalog import MAX_QUERY_RESULT_ROWS
from data_chat.data.connection import create_sql_server_engine
from data_chat.data.repository import CatalogRepository
from data_chat.llm.openai_intent import (
    InvalidLLMOutputError,
    OpenAIConfigurationError,
    OpenAIProviderError,
)
from data_chat.llm.langchain_adapters import (
    LangChainAnswerGenerator,
    LangChainIntentInterpreter,
    create_chat_model,
)
from data_chat.schemas.chat import ChatErrorResponse
from data_chat.services.conversations import ConversationStore
from data_chat.services.chat import (
    DataAccessError,
    DataAccessUnavailable,
    ChatWorkflow,
    InvalidAnswerError,
    QueryTimeoutError,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = Settings()
    configure_logging(settings.log_level)
    app.state.chat_workflow = None

    missing_settings: list[str] = []
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )
    connection_string = (
        settings.sql_server_odbc_connection_string.get_secret_value()
        if settings.sql_server_odbc_connection_string is not None
        else None
    )
    if _is_missing_setting(api_key):
        missing_settings.append("OPENAI_API_KEY")
    if _is_missing_setting(settings.openai_model):
        missing_settings.append("OPENAI_MODEL")
    if _is_missing_setting(connection_string):
        missing_settings.append("SQL_SERVER_ODBC_CONNECTION_STRING")

    engine: Engine | None = None
    repository: CatalogRepository | None = None
    try:
        if missing_settings:
            logger.info(
                "Chat workflow not configured; missing settings: %s",
                ", ".join(missing_settings),
            )
        else:
            chat_model = create_chat_model(settings)
            engine = create_sql_server_engine(settings)
            repository = CatalogRepository(
                engine,
                max_rows=MAX_QUERY_RESULT_ROWS,
            )
            app.state.chat_workflow = ChatWorkflow(
                LangChainIntentInterpreter(chat_model),
                repository,
                LangChainAnswerGenerator(chat_model),
                ConversationStore(),
            )
        yield
    finally:
        app.state.chat_workflow = None
        if repository is not None:
            repository.close()
        elif engine is not None:
            engine.dispose()


def _is_missing_setting(value: str | None) -> bool:
    return (
        value is None
        or not value.strip()
        or "replace-with-" in value.casefold()
    )


app = FastAPI(
    title="Data Chat API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(health_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning(
        "Rejected invalid API request: method=%s path=%s error_count=%s",
        request.method,
        request.url.path,
        len(exc.errors()),
    )
    body = ChatErrorResponse(
        error="request_invalid",
        message="The request does not match the required API contract.",
    )
    return JSONResponse(status_code=422, content=body.model_dump())


@app.exception_handler(ChatServiceUnavailable)
@app.exception_handler(DataAccessUnavailable)
@app.exception_handler(OpenAIConfigurationError)
async def handle_unavailable_error(_request: Request, _exc: Exception) -> JSONResponse:
    _log_safe_failure(_request, _exc)
    body = ChatErrorResponse(
        error="service_unavailable",
        message="Chat processing is not available right now.",
    )
    return JSONResponse(status_code=503, content=body.model_dump())


@app.exception_handler(OpenAIProviderError)
async def handle_provider_error(
    request: Request,
    exc: OpenAIProviderError,
) -> JSONResponse:
    _log_safe_failure(request, exc)
    body = ChatErrorResponse(
        error="upstream_error",
        message="An upstream service could not process the request.",
    )
    return JSONResponse(status_code=503, content=body.model_dump())


@app.exception_handler(QueryTimeoutError)
async def handle_query_timeout(
    request: Request,
    exc: QueryTimeoutError,
) -> JSONResponse:
    _log_safe_failure(request, exc)
    body = ChatErrorResponse(
        error="upstream_error",
        message="The data query took too long to complete.",
    )
    return JSONResponse(status_code=504, content=body.model_dump())


@app.exception_handler(DataAccessError)
async def handle_data_error(request: Request, exc: DataAccessError) -> JSONResponse:
    _log_safe_failure(request, exc)
    body = ChatErrorResponse(
        error="upstream_error",
        message="The approved data service could not complete the query.",
    )
    return JSONResponse(status_code=502, content=body.model_dump())


@app.exception_handler(InvalidLLMOutputError)
@app.exception_handler(InvalidAnswerError)
async def handle_invalid_upstream_response(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    _log_safe_failure(request, exc)
    body = ChatErrorResponse(
        error="upstream_invalid_response",
        message="An upstream service returned a response that could not be used.",
    )
    return JSONResponse(status_code=502, content=body.model_dump())


def _log_safe_failure(request: Request, exc: Exception) -> None:
    logger.warning(
        "Chat request failed: category=%s path=%s",
        type(exc).__name__,
        request.url.path,
    )
