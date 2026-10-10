"""Process-local, user-and-session-scoped conversation memory."""

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock, RLock


MAX_SESSIONS = 1000


@dataclass
class _SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    lock: RLock = field(default_factory=RLock)
    active_requests: int = 0


class ConversationStore:
    """Keep bounded RAG history separate for every user and chat session."""

    def __init__(self, max_sessions=MAX_SESSIONS):
        self.max_sessions = max_sessions
        self._sessions = OrderedDict()
        self._registry_lock = Lock()

    @contextmanager
    def use_session(self, user_id, session_id):
        """Lock a session for one complete turn and yield its mutable history."""

        key = (user_id, session_id)
        with self._registry_lock:
            state = self._sessions.get(key)
            if state is None:
                state = _SessionState()
                self._sessions[key] = state
            else:
                self._sessions.move_to_end(key)
            state.active_requests += 1

        state.lock.acquire()
        try:
            yield state.messages
        finally:
            state.lock.release()
            with self._registry_lock:
                state.active_requests -= 1
                self._evict_idle_sessions()

    def _evict_idle_sessions(self):
        while len(self._sessions) > self.max_sessions:
            idle_key = next(
                (
                    key
                    for key, state in self._sessions.items()
                    if state.active_requests == 0
                ),
                None,
            )
            if idle_key is None:
                return
            del self._sessions[idle_key]
