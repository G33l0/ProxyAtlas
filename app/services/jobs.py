"""Global job manager.

Tracks every long-running job (discovery, validation, intelligence, monitoring,
export, report) with state, progress and counters. Thread-safe so both the GUI
thread and worker threads can read/update. The UI subscribes via the event bus.
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import JobState, JobType
from app.core.events import Topics, bus


@dataclass
class Job:
    id: int
    job_type: JobType
    label: str
    state: JobState = JobState.QUEUED
    progress: float = 0.0  # 0..100
    total: int = 0
    success: int = 0
    failures: int = 0
    errors: int = 0
    detail: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.job_type.value,
            "label": self.label,
            "state": self.state.value,
            "progress": round(self.progress, 1),
            "total": self.total,
            "success": self.success,
            "failures": self.failures,
            "errors": self.errors,
            "detail": self.detail,
            "duration": self.duration,
        }


class JobManager:
    """Central registry of jobs."""

    def __init__(self) -> None:
        self._jobs: dict[int, Job] = {}
        self._counter = itertools.count(1)
        self._lock = threading.RLock()

    def create(self, job_type: JobType, label: str, total: int = 0) -> Job:
        with self._lock:
            job = Job(id=next(self._counter), job_type=job_type, label=label, total=total)
            self._jobs[job.id] = job
        bus.publish(Topics.JOB_CREATED, job.snapshot())
        return job

    def start(self, job: Job) -> None:
        with self._lock:
            job.state = JobState.RUNNING
            job.started_at = time.time()
        self._emit(job)

    def update(
        self,
        job: Job,
        *,
        progress: float | None = None,
        success: int | None = None,
        failures: int | None = None,
        errors: int | None = None,
        detail: str | None = None,
        total: int | None = None,
    ) -> None:
        with self._lock:
            if progress is not None:
                job.progress = progress
            if success is not None:
                job.success = success
            if failures is not None:
                job.failures = failures
            if errors is not None:
                job.errors = errors
            if detail is not None:
                job.detail = detail
            if total is not None:
                job.total = total
        self._emit(job)

    def set_state(self, job: Job, state: JobState, detail: str | None = None) -> None:
        with self._lock:
            job.state = state
            if detail is not None:
                job.detail = detail
            if state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
                job.finished_at = time.time()
                if state == JobState.COMPLETED:
                    job.progress = 100.0
        self._emit(job)
        if state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            bus.publish(Topics.JOB_FINISHED, job.snapshot())

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.id, reverse=True)

    def active_jobs(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs.values() if j.state in (JobState.RUNNING, JobState.PAUSED, JobState.QUEUED)]

    def clear_finished(self) -> int:
        with self._lock:
            finished = [
                jid for jid, j in self._jobs.items()
                if j.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)
            ]
            for jid in finished:
                del self._jobs[jid]
        return len(finished)

    def _emit(self, job: Job) -> None:
        bus.publish(Topics.JOB_UPDATED, job.snapshot())


# Application-wide default job manager.
job_manager = JobManager()
