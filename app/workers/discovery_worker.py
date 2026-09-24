"""Discovery worker — runs a discovery provider and stores candidates."""

from __future__ import annotations

from typing import Any

from app.core.models import ProxyCandidate
from app.database import repository as repo
from app.services.app_context import AppContext
from app.testing.engine import JobControl
from app.workers.base import AsyncWorker


class DiscoveryWorker(AsyncWorker):
    """Run a discovery provider, streaming candidates into the discovery queue."""

    def __init__(
        self,
        ctx: AppContext,
        provider_key: str,
        config: dict[str, Any],
        control: JobControl | None = None,
        persist: bool = True,
        parent=None,
    ) -> None:
        self.ctx = ctx
        self.provider_key = provider_key
        self.config = config
        self.control = control or JobControl()
        self.persist = persist
        super().__init__(self._make_coro, parent)

    def stop(self) -> None:
        self.control.stop()

    async def _make_coro(self, worker: AsyncWorker):
        provider = self.ctx.discovery.build(self.provider_key, self.config)
        found = 0
        new = 0
        batch: list[ProxyCandidate] = []

        def on_candidate(cand: ProxyCandidate) -> None:
            nonlocal found
            found += 1
            batch.append(cand)
            worker.emit_item(cand)
            if found % 25 == 0:
                worker.emit_progress({"found": found, "new": new})

        outcome = await self.ctx.discovery.run(
            provider,
            on_candidate=on_candidate,
            should_stop=lambda: self.control.is_stopped,
            dedupe=True,
        )

        if self.persist and outcome.candidates:
            with self.ctx.database.session() as session:
                for cand in outcome.candidates:
                    _, is_new = repo.add_discovery_candidate(session, cand, self.ctx.cipher)
                    if is_new:
                        new += 1
                repo.add_audit(
                    session, "discovery", f"{provider.name()}: {new} new candidates"
                )
        worker.emit_progress({"found": len(outcome.candidates), "new": new})
        return {
            "provider": outcome.provider,
            "found": len(outcome.candidates),
            "new": new,
            "errors": outcome.errors,
        }
