import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class _ModelCounters:
    minute_window: deque = field(default_factory=deque)  # timestamps within last 60s
    day_window: deque = field(default_factory=deque)  # timestamps within last 24h


class LocalRateLimiter:
    """Tracks our own request counts per model so we can preemptively skip a
    model we know is exhausted, instead of waiting for a 429. This is a
    best-effort guard, not a guarantee — the provider's own limits are the
    source of truth, and RateLimitError from the provider is still handled."""

    def __init__(self, limits: dict[str, dict]):
        # limits: {"gemini-2.5-flash": {"rpm": 15, "tpm": ..., "rpd": 1500}, ...}
        self.limits = limits
        self._counters: dict[str, _ModelCounters] = {}

    def _get(self, model: str) -> _ModelCounters:
        if model not in self._counters:
            self._counters[model] = _ModelCounters()
        return self._counters[model]

    def _prune(self, counters: _ModelCounters, now: float) -> None:
        while counters.minute_window and now - counters.minute_window[0] > 60:
            counters.minute_window.popleft()
        while counters.day_window and now - counters.day_window[0] > 86400:
            counters.day_window.popleft()

    def can_call(self, model: str) -> bool:
        limit = self.limits.get(model)
        if not limit:
            return True  # unknown model (e.g. local ollama) — no local cap
        counters = self._get(model)
        now = time.time()
        self._prune(counters, now)

        rpm = limit.get("rpm")
        rpd = limit.get("rpd")
        if rpm is not None and len(counters.minute_window) >= rpm:
            return False
        if rpd is not None and len(counters.day_window) >= rpd:
            return False
        return True

    def record_call(self, model: str) -> None:
        counters = self._get(model)
        now = time.time()
        counters.minute_window.append(now)
        counters.day_window.append(now)
