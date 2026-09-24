"""Concurrent validation engine with pause/resume/stop.

Runs :func:`validate_proxy` across many candidates using a bounded
``asyncio.Semaphore`` (no thread-per-proxy). Control flags are
:class:`threading.Event` objects so the GUI thread can pause/resume/stop
safely without touching the event loop. Progress is reported via callbacks.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from app.core.enums import ValidationStatus
from app.core.models import Endpoint, ValidationResult
from app.testing.profiles import ValidationProfile
from app.testing.validator import detect_public_ip, validate_proxy

logger = logging.getLogger("proxyatlas.jobs")


@dataclass
class ValidationStats:
    total: int = 0
    queued: int = 0
    testing: int = 0
    working: int = 0
    failed: int = 0
    timeouts: int = 0
    auth_required: int = 0
    completed: int = 0
    latency_sum: float = 0.0
    latency_count: int = 0
    start_time: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.completed == 0:
            return 0.0
        return round(100.0 * self.working / self.completed, 1)

    @property
    def avg_latency(self) -> float:
        if self.latency_count == 0:
            return 0.0
        return round(self.latency_sum / self.latency_count, 1)

    def throughput(self, now: float) -> float:
        elapsed = max(now - self.start_time, 0.001)
        return round(self.completed / elapsed, 2)

    def snapshot(self, now: float) -> dict[str, float | int]:
        return {
            "total": self.total,
            "queued": self.queued,
            "testing": self.testing,
            "working": self.working,
            "failed": self.failed,
            "timeouts": self.timeouts,
            "auth_required": self.auth_required,
            "completed": self.completed,
            "success_rate": self.success_rate,
            "avg_latency": self.avg_latency,
            "throughput": self.throughput(now),
        }


class JobControl:
    """Thread-safe pause/resume/stop flags shared with the GUI."""

    def __init__(self) -> None:
        self._paused = threading.Event()
        self._stopped = threading.Event()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def stop(self) -> None:
        self._stopped.set()

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    @property
    def is_stopped(self) -> bool:
        return self._stopped.is_set()

    async def wait_if_paused(self, poll: float = 0.15) -> None:
        while self._paused.is_set() and not self._stopped.is_set():
            await asyncio.sleep(poll)


class ValidationEngine:
    """Drives concurrent validation of a batch of endpoints."""

    def __init__(
        self,
        profile: ValidationProfile,
        validation_endpoints: list[str],
        judge_endpoint: str | None,
        concurrency: int = 40,
        control: JobControl | None = None,
    ) -> None:
        self.profile = profile
        self.validation_endpoints = validation_endpoints
        self.judge_endpoint = judge_endpoint
        self.concurrency = max(1, int(concurrency))
        self.control = control or JobControl()
        self.stats = ValidationStats()

    async def run(
        self,
        endpoints: Iterable[Endpoint],
        on_result: Callable[[ValidationResult], None] | None = None,
        on_progress: Callable[[dict], None] | None = None,
    ) -> list[ValidationResult]:
        import time

        endpoints = list(endpoints)
        self.stats = ValidationStats(
            total=len(endpoints), queued=len(endpoints), start_time=time.perf_counter()
        )
        results: list[ValidationResult] = []
        semaphore = asyncio.Semaphore(self.concurrency)
        lock = asyncio.Lock()

        real_ip = None
        if self.profile.header_analysis or self.profile.dns_analysis:
            real_ip = await detect_public_ip(self.validation_endpoints)

        async def worker(ep: Endpoint) -> None:
            if self.control.is_stopped:
                return
            await self.control.wait_if_paused()
            if self.control.is_stopped:
                return
            async with semaphore:
                async with lock:
                    self.stats.queued = max(0, self.stats.queued - 1)
                    self.stats.testing += 1
                try:
                    res = await validate_proxy(
                        ep,
                        self.profile,
                        self.validation_endpoints,
                        self.judge_endpoint,
                        real_ip,
                    )
                except Exception as exc:  # noqa: BLE001 - safety net
                    logger.exception("Validator crashed for %s", ep.identity)
                    res = ValidationResult(
                        endpoint=ep,
                        status=ValidationStatus.FAILED,
                        error_category="engine",
                        error_detail=str(exc),
                    )
                async with lock:
                    self.stats.testing = max(0, self.stats.testing - 1)
                    self.stats.completed += 1
                    self._tally(res)
                    results.append(res)
                    now = time.perf_counter()
                    snap = self.stats.snapshot(now)
                if on_result:
                    on_result(res)
                if on_progress:
                    on_progress(snap)

        tasks = [asyncio.create_task(worker(ep)) for ep in endpoints]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return results

    def _tally(self, res: ValidationResult) -> None:
        if res.status == ValidationStatus.WORKING:
            self.stats.working += 1
            if res.latency_ms is not None:
                self.stats.latency_sum += res.latency_ms
                self.stats.latency_count += 1
        elif res.status == ValidationStatus.TIMEOUT:
            self.stats.timeouts += 1
            self.stats.failed += 1
        elif res.status == ValidationStatus.AUTH_REQUIRED:
            self.stats.auth_required += 1
            self.stats.failed += 1
        else:
            self.stats.failed += 1
