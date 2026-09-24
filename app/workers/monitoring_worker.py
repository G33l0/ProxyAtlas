"""Monitoring worker — runs one monitoring pass in the background."""

from __future__ import annotations

from app.services.app_context import AppContext
from app.services.monitoring import run_monitor_once
from app.workers.base import AsyncWorker


class MonitoringWorker(AsyncWorker):
    def __init__(
        self,
        ctx: AppContext,
        job_id: int,
        target_type: str,
        target_ref: str,
        parent=None,
    ) -> None:
        self.ctx = ctx
        self.job_id = job_id
        self.target_type = target_type
        self.target_ref = target_ref
        super().__init__(self._make_coro, parent)

    async def _make_coro(self, worker: AsyncWorker):
        outcome = await run_monitor_once(
            self.ctx, self.job_id, self.target_type, self.target_ref
        )
        worker.emit_progress(
            {"total": outcome.total, "working": outcome.working, "failed": outcome.failed}
        )
        return outcome
