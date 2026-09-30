"""Kill switch and entry rate limits.

Overtrading is the most consistent loss pattern in live LLM trading: the Alpha
Arena Season 1 winner placed about 43 trades in two weeks while losers placed
hundreds to over a thousand. These limits are deterministic and sit outside
anything a model can argue with.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone


class TradingGuard:
    """Global halt plus rolling caps on new entries.

    Exits are never blocked here: closing risk must always be possible.
    """

    def __init__(self, *, max_entries_per_hour: int = 2, max_entries_per_day: int = 6) -> None:
        self.max_entries_per_hour = max_entries_per_hour
        self.max_entries_per_day = max_entries_per_day
        self._entries: deque[datetime] = deque()
        self._halt_reason: str | None = None

    @property
    def halted(self) -> bool:
        return self._halt_reason is not None

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason

    def halt(self, reason: str) -> None:
        """Trip the kill switch. Pair with a provider's `close_all_positions()` to flatten."""
        self._halt_reason = reason or "manual halt"

    def resume(self) -> None:
        self._halt_reason = None

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=1)
        while self._entries and self._entries[0] <= cutoff:
            self._entries.popleft()

    def check(self, now: datetime | None = None) -> list[str]:
        """Reasons a new entry is blocked right now; empty means allowed."""
        now = now or datetime.now(timezone.utc)
        self._prune(now)
        reasons: list[str] = []
        if self._halt_reason is not None:
            reasons.append(f"trading halted: {self._halt_reason}")
        last_hour = sum(1 for ts in self._entries if ts > now - timedelta(hours=1))
        if last_hour >= self.max_entries_per_hour:
            reasons.append("hourly entry limit reached")
        if len(self._entries) >= self.max_entries_per_day:
            reasons.append("daily entry limit reached")
        return reasons

    def record_entry(self, now: datetime | None = None) -> None:
        self._entries.append(now or datetime.now(timezone.utc))
