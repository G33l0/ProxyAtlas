"""Small thread-safe pub/sub bus. Engine code publishes progress here without
pulling in Qt; the UI subscribes and re-emits on Qt signals.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any


class EventBus:
    """Minimal synchronous publish/subscribe bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> Callable[[], None]:
        """Register `callback` for `topic`. Returns an unsubscribe func."""
        with self._lock:
            self._subscribers[topic].append(callback)

        def _unsub() -> None:
            with self._lock:
                if callback in self._subscribers.get(topic, []):
                    self._subscribers[topic].remove(callback)

        return _unsub

    def publish(self, topic: str, payload: Any = None) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(topic, []))
        for cb in callbacks:
            try:
                cb(payload)
            except Exception:  # pragma: no cover - subscriber errors isolated
                import logging

                logging.getLogger(__name__).exception("Event subscriber failed for %s", topic)

    def clear(self) -> None:
        with self._lock:
            self._subscribers.clear()


# Common topic names.
class Topics:
    JOB_CREATED = "job.created"
    JOB_UPDATED = "job.updated"
    JOB_FINISHED = "job.finished"
    DISCOVERY_CANDIDATE = "discovery.candidate"
    VALIDATION_RESULT = "validation.result"
    PROXY_UPSERTED = "proxy.upserted"
    MONITORING_TICK = "monitoring.tick"


# Application-wide default bus.
bus = EventBus()
