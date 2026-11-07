
"""In-process limits on paid model investigations.

The global hourly cap is the hard bound on spending, because a
visitor can always discard their guest cookie. Limits are per
Uvicorn process; the deployment runs a single worker.
"""

import os
import threading
import time
from collections import deque


class InferenceBudget:

    def __init__(
        self,
        *,
        per_session_per_hour,
        global_per_hour,
        max_concurrent,
        clock=time.monotonic,
    ):
        self.per_session_per_hour = per_session_per_hour
        self.global_per_hour = global_per_hour
        self.max_concurrent = max_concurrent
        self.clock = clock

        self._lock = threading.Lock()
        self._global = deque()
        self._sessions = {}
        self._running = 0

    def acquire(self, session_key):
        """Reserve one run, or return the reason it is refused."""

        with self._lock:
            now = self.clock()
            self._expire(now)

            runs = self._sessions.setdefault(session_key, deque())

            if self._running >= self.max_concurrent:
                return (
                    "Another investigation is already running. "
                    "Try again in a moment."
                )

            if len(self._global) >= self.global_per_hour:
                return (
                    "The demo's hourly AI investigation budget is "
                    "used up. Try again later."
                )

            if len(runs) >= self.per_session_per_hour:
                return (
                    "This demo case has reached its hourly AI "
                    "investigation limit. Try again later."
                )

            self._global.append(now)
            runs.append(now)
            self._running += 1

            return None

    def release(self):
        with self._lock:
            self._running -= 1

    def _expire(self, now):
        cutoff = now - 3600

        while self._global and self._global[0] <= cutoff:
            self._global.popleft()

        for key in list(self._sessions):
            runs = self._sessions[key]

            while runs and runs[0] <= cutoff:
                runs.popleft()

            if not runs:
                del self._sessions[key]


def budget_from_environment():
    return InferenceBudget(
        per_session_per_hour=int(
            os.getenv("FOLLOWUP_AI_RUNS_PER_SESSION_HOUR", "5")
        ),
        global_per_hour=int(
            os.getenv("FOLLOWUP_AI_RUNS_PER_HOUR", "60")
        ),
        max_concurrent=int(
            os.getenv("FOLLOWUP_AI_MAX_CONCURRENT", "2")
        ),
    )
