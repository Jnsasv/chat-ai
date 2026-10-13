from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from data_chat.services.conversations import (
    MAX_STORED_ANSWER_CHARS,
    ConversationStore,
    ConversationTurn,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_history_is_empty_for_unknown_conversations() -> None:
    assert ConversationStore().history(uuid4()) == ()


def test_turns_are_kept_in_order_and_bounded() -> None:
    store = ConversationStore(max_turns=2)
    conversation_id = uuid4()

    for index in range(3):
        store.append(conversation_id, f"q{index}", f"a{index}")

    assert store.history(conversation_id) == (
        ConversationTurn("q1", "a1"),
        ConversationTurn("q2", "a2"),
    )


def test_stored_answers_are_truncated() -> None:
    store = ConversationStore()
    conversation_id = uuid4()

    store.append(conversation_id, "q", "x" * (MAX_STORED_ANSWER_CHARS + 100))

    assert len(store.history(conversation_id)[0].answer) == MAX_STORED_ANSWER_CHARS


def test_conversations_are_isolated() -> None:
    store = ConversationStore()
    first, second = uuid4(), uuid4()

    store.append(first, "q", "a")

    assert store.history(second) == ()


def test_expired_conversations_are_evicted() -> None:
    clock = Clock()
    store = ConversationStore(ttl_seconds=60, clock=clock)
    conversation_id = uuid4()
    store.append(conversation_id, "q", "a")

    clock.now = 61

    assert store.history(conversation_id) == ()


def test_oldest_conversation_is_evicted_at_capacity() -> None:
    store = ConversationStore(max_conversations=2)
    first, second, third = uuid4(), uuid4(), uuid4()

    store.append(first, "q", "a")
    store.append(second, "q", "a")
    store.append(third, "q", "a")

    assert store.history(first) == ()
    assert store.history(second) != ()
    assert store.history(third) != ()


@pytest.mark.parametrize(
    "limits",
    [{"max_conversations": 0}, {"max_turns": 0}, {"ttl_seconds": 0}],
)
def test_invalid_limits_are_rejected(limits: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        ConversationStore(**limits)
