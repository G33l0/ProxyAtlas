"""Validation worker - runs the processing pipeline in the background."""

from __future__ import annotations

from collections.abc import Iterable

from app.core.models import ProxyCandidate
from app.services.app_context import AppContext
from app.services.pipeline import ProcessingPipeline
from app.testing.engine import JobControl
from app.testing.profiles import get_profile
from app.workers.base import AsyncWorker


class ValidationWorker(AsyncWorker):
    """Validate + enrich + persist a batch of candidates."""

    def __init__(
        self,
        ctx: AppContext,
        candidates: Iterable[ProxyCandidate],
        profile_name: str = "standard",
        concurrency: int | None = None,
        control: JobControl | None = None,
        parent=None,
    ) -> None:
        self.ctx = ctx
        self.candidates = list(candidates)
        self.profile_name = profile_name
        self.concurrency = concurrency
        self.control = control or JobControl()
        super().__init__(self._make_coro, parent)

    def pause(self) -> None:
        self.control.pause()

    def resume(self) -> None:
        self.control.resume()

    def stop(self) -> None:
        self.control.stop()

    async def _make_coro(self, worker: AsyncWorker):
        profile = get_profile(self.profile_name, self.ctx.custom_profiles())
        timeout = float(self.ctx.settings.get("testing", "timeout", 12.0))
        profile.timeout = timeout
        pipeline = ProcessingPipeline(
            db=self.ctx.database,
            cipher=self.ctx.cipher,
            intelligence=self.ctx.intelligence,
            settings=self.ctx.testing_settings(),
            intelligence_enabled=self.ctx.intelligence_enabled(),
        )
        return await pipeline.process(
            self.candidates,
            profile,
            control=self.control,
            on_progress=lambda snap: worker.emit_progress(snap),
            on_result=lambda res: worker.emit_item(res),
            concurrency=self.concurrency,
        )
