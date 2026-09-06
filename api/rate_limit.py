"""Thread-safe sliding-window rate limits for the bounded public demo."""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class RateLimitDecision:
    """Describe whether a request may proceed and when capacity returns."""

    allowed: bool
    remaining: int
    retry_after_seconds: int = 0


class SlidingWindowRateLimiter:
    """Bound requests per key without adding an external service dependency."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        if max_requests < 1 or window_seconds < 1:
            raise ValueError("rate limit values must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, now: float | None = None) -> RateLimitDecision:
        """Consume one request when capacity is available for the supplied key."""

        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_requests:
                retry_after = max(1, math.ceil(events[0] + self.window_seconds - current))
                return RateLimitDecision(False, 0, retry_after)
            events.append(current)
            return RateLimitDecision(True, self.max_requests - len(events))
