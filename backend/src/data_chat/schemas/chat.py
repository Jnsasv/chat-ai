from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

ChatStatus = Literal[
    "answered",
    "clarification_required",
    "unsupported",
    "insufficient_data",
]


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    label: str
    urls: list[HttpUrl] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    message_id: UUID
    answer: str
    status: ChatStatus
    sources: list[ChatSource] = Field(default_factory=list)


class ChatErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: Literal[
        "service_unavailable",
        "upstream_error",
        "upstream_invalid_response",
        "request_invalid",
    ]
    message: str


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    status: Literal["answered", "insufficient_data"]
    answer: str = Field(min_length=1, max_length=2000)
