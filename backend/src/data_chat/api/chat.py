from fastapi import APIRouter, Depends, Request

from data_chat.schemas.chat import (
    ChatErrorResponse,
    ChatMessageRequest,
    ChatMessageResponse,
)
from data_chat.services.chat import ChatWorkflow

router = APIRouter()


class ChatServiceUnavailable(RuntimeError):
    pass


def get_chat_workflow(request: Request) -> ChatWorkflow | None:
    workflow = getattr(request.app.state, "chat_workflow", None)
    return workflow if isinstance(workflow, ChatWorkflow) else None


@router.post(
    "/chat/messages",
    response_model=ChatMessageResponse,
    tags=["chat"],
    responses={
        422: {"model": ChatErrorResponse, "description": "Invalid request."},
        502: {"model": ChatErrorResponse, "description": "Upstream or data error."},
        503: {"model": ChatErrorResponse, "description": "Service unavailable."},
        504: {"model": ChatErrorResponse, "description": "Query timed out."},
    },
)
def post_chat_message(
    message: ChatMessageRequest,
    workflow: ChatWorkflow | None = Depends(get_chat_workflow),
) -> ChatMessageResponse:
    if workflow is None:
        raise ChatServiceUnavailable("The chat workflow is not configured.")
    return workflow.respond(message)
