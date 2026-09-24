"""Base async worker running an asyncio loop inside a QThread."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("proxyatlas.jobs")


class AsyncWorker(QThread):
    """Runs a coroutine factory in a dedicated event loop.

    Signals:
        progress(dict)   — periodic progress snapshots
        item(object)     — a streamed result/candidate
        failed(str)      — an unrecoverable error message
        completed(object)— the coroutine's return value on success
    """

    progress = pyqtSignal(dict)
    item = pyqtSignal(object)
    failed = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, coro_factory: Callable[[AsyncWorker], Awaitable], parent=None) -> None:
        super().__init__(parent)
        self._coro_factory = coro_factory
        self._loop: asyncio.AbstractEventLoop | None = None

    def run(self) -> None:  # noqa: D401 - QThread entry point
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._coro_factory(self))
            self.completed.emit(result)
        except Exception as exc:  # noqa: BLE001 - surface to GUI
            logger.exception("Worker failed")
            self.failed.emit(str(exc))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # pragma: no cover
                pass
            loop.close()
            self._loop = None

    # Thread-safe signal helpers usable from inside the coroutine.
    def emit_progress(self, snapshot: dict) -> None:
        self.progress.emit(snapshot)

    def emit_item(self, obj: object) -> None:
        self.item.emit(obj)
