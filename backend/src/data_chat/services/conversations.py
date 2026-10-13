from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import UUID

MAX_STORED_ANSWER_CHARS = 500


@dataclass(frozen=True)
class ConversationTurn:
    question: str
    answer: str


class ConversationStore:
    """Bounded in-memory history keyed by conversation ID.

    History is lost on restart and is never returned to clients; it is only
    given to the intent step so follow-up questions can be resolved.
    """

    def __init__(
        self,
        *,
        max_conversations: int = 1000,
        max_turns: int = 6,
        ttl_seconds: float = 1800,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_conversations < 1 or max_turns < 1 or ttl_seconds <= 0:
            raise ValueError("Conversation store limits must be positive.")
        self._max_conversations = max_conversations
        self._max_turns = max_turns
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = Lock()
        self._conversations: OrderedDict[
            UUID, tuple[float, list[ConversationTurn]]
        ] = OrderedDict()

    def history(self, conversation_id: UUID) -> tuple[ConversationTurn, ...]:
        with self._lock:
            self._evict_expired()
            entry = self._conversations.get(conversation_id)
            return tuple(entry[1]) if entry else ()

    def append(self, conversation_id: UUID, question: str, answer: str) -> None:
        turn = ConversationTurn(
            question=question,
            answer=answer[:MAX_STORED_ANSWER_CHARS],
        )
        with self._lock:
            self._evict_expired()
            entry = self._conversations.pop(conversation_id, None)
            turns = entry[1] if entry else []
            turns.append(turn)
            self._conversations[conversation_id] = (
                self._clock(),
                turns[-self._max_turns :],
            )
            while len(self._conversations) > self._max_conversations:
                self._conversations.popitem(last=False)

    def _evict_expired(self) -> None:
        cutoff = self._clock() - self._ttl_seconds
        while self._conversations:
            oldest_id, (touched_at, _) = next(iter(self._conversations.items()))
            if touched_at >= cutoff:
                break
            del self._conversations[oldest_id]
