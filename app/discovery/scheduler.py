"""Works out which recurring items are due from last_run + interval. It only
decides; the services layer / a Qt timer does the firing, which keeps this
testable without a loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ScheduledItem:
    key: str
    interval_minutes: int
    last_run: datetime | None = None
    enabled: bool = True
    metadata: dict = field(default_factory=dict)

    def is_due(self, now: datetime | None = None) -> bool:
        if not self.enabled:
            return False
        now = now or _now()
        if self.last_run is None:
            return True
        return now >= self.last_run + timedelta(minutes=self.interval_minutes)

    def next_run(self) -> datetime:
        base = self.last_run or _now()
        return base + timedelta(minutes=self.interval_minutes)


class Scheduler:
    """Tracks scheduled items and reports which are due."""

    def __init__(self) -> None:
        self._items: dict[str, ScheduledItem] = {}

    def upsert(self, item: ScheduledItem) -> None:
        self._items[item.key] = item

    def remove(self, key: str) -> None:
        self._items.pop(key, None)

    def due_items(self, now: datetime | None = None) -> list[ScheduledItem]:
        now = now or _now()
        return [it for it in self._items.values() if it.is_due(now)]

    def mark_run(self, key: str, when: datetime | None = None) -> None:
        item = self._items.get(key)
        if item is not None:
            item.last_run = when or _now()

    def all_items(self) -> list[ScheduledItem]:
        return list(self._items.values())
