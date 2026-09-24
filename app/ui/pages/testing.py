"""Testing page: run validation jobs with live stats and pause/resume/stop."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSpinBox,
)

from app.core.enums import Protocol
from app.core.models import Endpoint, ProxyCandidate
from app.database import repository as repo
from app.database.filters import FilterSpec
from app.testing.engine import JobControl
from app.ui.pages.base import BasePage
from app.ui.widgets.common import Card, StatCard
from app.workers.validation_worker import ValidationWorker

TARGETS = [
    ("Discovery queue", "queue"),
    ("All proxies", "all"),
    ("Working proxies", "working"),
    ("Failed proxies", "failed"),
]


class TestingPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Testing", "Validate proxies with controlled concurrency")
        self._worker: ValidationWorker | None = None
        self._control: JobControl | None = None

        controls = Card()
        cl = QHBoxLayout(controls)
        cl.addWidget(QLabel("Target:"))
        self.target_combo = QComboBox()
        for label, key in TARGETS:
            self.target_combo.addItem(label, key)
        cl.addWidget(self.target_combo)
        cl.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self._reload_profiles()
        cl.addWidget(self.profile_combo)
        cl.addWidget(QLabel("Concurrency:"))
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 500)
        self.concurrency.setValue(int(ctx.settings.get("testing", "concurrency", 40)))
        cl.addWidget(self.concurrency)
        cl.addStretch(1)
        self.root.addWidget(controls)

        btns = QHBoxLayout()
        self.start_btn = self._btn("Start", self._start, primary=True)
        self.pause_btn = self._btn("Pause", self._pause)
        self.resume_btn = self._btn("Resume", self._resume)
        self.stop_btn = self._btn("Stop", self._stop)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        for b in (self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        self.root.addLayout(btns)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.root.addWidget(self.progress)

        # Live stat cards.
        grid = QGridLayout()
        grid.setSpacing(10)
        self._stats: dict[str, StatCard] = {}
        specs = [
            ("total", "Total"), ("queued", "Queued"), ("testing", "Testing"),
            ("working", "Working"), ("failed", "Failed"), ("timeouts", "Timeouts"),
            ("success_rate", "Success Rate %"), ("avg_latency", "Avg Latency ms"),
            ("throughput", "Throughput /s"),
        ]
        for i, (key, label) in enumerate(specs):
            card = StatCard(label)
            self._stats[key] = card
            grid.addWidget(card, i // 3, i % 3)
        self.root.addLayout(grid)
        self.root.addStretch(1)

    def _btn(self, text, slot, primary=False):
        from PyQt6.QtWidgets import QPushButton

        b = QPushButton(text)
        if primary:
            b.setObjectName("Primary")
        b.clicked.connect(slot)
        return b

    def _reload_profiles(self) -> None:
        self.profile_combo.clear()
        from app.testing.profiles import BUILTIN_PROFILES

        names = list(BUILTIN_PROFILES.keys()) + list(self.ctx.custom_profiles().keys())
        self.profile_combo.addItems(names)
        default = self.ctx.settings.get("testing", "default_profile", "standard")
        idx = self.profile_combo.findText(default)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

    def on_shown(self) -> None:
        self._reload_profiles()

    # --- job control --------------------------------------------------------
    def _gather_candidates(self) -> list[ProxyCandidate]:
        target = self.target_combo.currentData()
        candidates: list[ProxyCandidate] = []
        with self.ctx.database.session() as session:
            if target == "queue":
                for row in repo.list_discovery_results(session):
                    candidates.append(repo.discovery_result_to_candidate(row, self.ctx.cipher))
            else:
                spec = FilterSpec()
                if target == "working":
                    spec.add("status", "eq", "working")
                elif target == "failed":
                    spec.add("status", "eq", "failed")
                for p in repo.query_proxies(session, spec, limit=20000):
                    user, pw = repo.get_credentials(session, p, self.ctx.cipher)
                    ep = Endpoint(p.host, p.port, Protocol.from_value(p.protocol, Protocol.HTTP), user, pw)
                    candidates.append(ProxyCandidate(ep, source=p.source))
        return candidates

    def _start(self) -> None:
        candidates = self._gather_candidates()
        if not candidates:
            self.toast("Nothing to test for the selected target", "warning")
            return
        self._control = JobControl()
        self._worker = ValidationWorker(
            self.ctx, candidates, self.profile_combo.currentText(),
            concurrency=self.concurrency.value(), control=self._control,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.completed.connect(self._on_done)
        self._worker.failed.connect(lambda e: self.toast(f"Testing failed: {e}", "error"))
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        self._worker.start()
        self.toast(f"Testing {len(candidates)} prox{'y' if len(candidates)==1 else 'ies'}…", "info")

    def _on_progress(self, snap: dict) -> None:
        for key, card in self._stats.items():
            if key in snap:
                val = snap[key]
                card.set_value(f"{val:.0f}" if isinstance(val, float) and key not in ("success_rate", "throughput", "avg_latency") else val)
        total = snap.get("total", 0) or 1
        completed = snap.get("completed", 0)
        self.progress.setValue(int(100 * completed / total))

    def _on_done(self, res) -> None:
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.progress.setValue(100)
        self.toast(f"Testing complete: {res.working} working / {res.total}", "success")
        self._worker = None
        self.main.notify_proxies_changed()

    def _pause(self) -> None:
        if self._control:
            self._control.pause()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.toast("Paused", "info")

    def _resume(self) -> None:
        if self._control:
            self._control.resume()
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.toast("Resumed", "info")

    def _stop(self) -> None:
        if self._control:
            self._control.stop()
            self.toast("Stopping…", "info")
