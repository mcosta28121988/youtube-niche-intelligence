"""Track estimated YouTube Data API quota usage for a pipeline run."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# search.list has its own daily allowance (counted in calls); other read
# endpoints draw 1 unit per call from the shared 10,000-unit daily budget.
SEARCH_ENDPOINT = "search.list"


@dataclass
class QuotaTracker:
    """Counts API requests per endpoint. Retries are not counted (estimate)."""

    calls: Counter[str] = field(default_factory=Counter)

    def record(self, endpoint: str) -> None:
        self.calls[endpoint] += 1

    @property
    def search_calls(self) -> int:
        return self.calls[SEARCH_ENDPOINT]

    @property
    def units(self) -> int:
        """Units consumed from the shared daily budget (excludes search.list)."""
        return sum(count for endpoint, count in self.calls.items() if endpoint != SEARCH_ENDPOINT)
