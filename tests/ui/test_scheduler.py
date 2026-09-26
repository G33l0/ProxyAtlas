"""Test the background monitoring scheduler in the main window."""

import json

import pytest

from app.database import repository as repo

pytest.importorskip("PyQt6.QtWidgets")


def test_scheduler_fires_due_job(ctx, qtbot):
    from app.ui.main_window import MainWindow

    # A monitoring job with next_run_at=None is immediately due.
    with ctx.database.session() as s:
        job = repo.upsert_monitoring_job(
            s, "auto", "filter",
            json.dumps({"conditions": [], "combine": "and", "search": None}), 30,
        )
        job_id = job.id

    win = MainWindow(ctx)
    qtbot.addWidget(win)

    # Fire a tick manually (rather than waiting 60s).
    win._tick_monitors()
    assert job_id in win._active_monitor_jobs

    # The worker runs quickly on an empty DB (no network); wait for the
    # completion callback to clear the active set (implies the run finished).
    qtbot.waitUntil(lambda: job_id not in win._active_monitor_jobs, timeout=15000)
    with ctx.database.session() as s:
        history = repo.monitoring_history(s, job_id)
        assert len(history) >= 1
        assert history[-1].total == 0  # empty DB -> nothing to monitor, but a run happened


def test_scheduler_skips_disabled_and_active(ctx, qtbot):
    from app.ui.main_window import MainWindow

    with ctx.database.session() as s:
        job = repo.upsert_monitoring_job(
            s, "disabled", "filter", "{}", 30, enabled=False,
        )
        disabled_id = job.id

    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win._tick_monitors()
    assert disabled_id not in win._active_monitor_jobs  # disabled never fires
