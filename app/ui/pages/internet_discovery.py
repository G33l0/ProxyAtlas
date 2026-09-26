"""Internet Discovery page - generate candidates over authorized address space."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from app.database import repository as repo
from app.testing.engine import JobControl
from app.ui.pages.base import BasePage
from app.ui.widgets.common import Card, StatCard
from app.workers.discovery_worker import DiscoveryWorker
from app.workers.validation_worker import ValidationWorker


class InternetDiscoveryPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(
            ctx, main_window, "Internet Discovery",
            "Generate proxy candidates across authorized CIDR ranges - all enter the standard pipeline",
        )
        self._workers: list = []
        self._control: JobControl | None = None
        self._generated = 0

        config_card = Card()
        form = QFormLayout(config_card)
        self.profile_edit = QLineEdit("default")
        self.cidrs_edit = QPlainTextEdit()
        self.cidrs_edit.setPlaceholderText("One CIDR per line, e.g.\n203.0.113.0/24\n198.51.100.0/24")
        self.cidrs_edit.setFixedHeight(80)
        self.ports_edit = QLineEdit("8080,3128,1080,8888,80")
        self.max_spin = QSpinBox()
        self.max_spin.setRange(1, 200000)
        self.max_spin.setValue(1000)
        form.addRow("Discovery profile", self.profile_edit)
        form.addRow("Target CIDR ranges", self.cidrs_edit)
        form.addRow("Ports", self.ports_edit)
        form.addRow("Max candidates", self.max_spin)
        self.root.addWidget(config_card)

        btns = QHBoxLayout()
        self.generate_btn = QPushButton("Generate Candidates")
        self.generate_btn.setObjectName("Primary")
        self.generate_btn.clicked.connect(self._generate)
        self.validate_btn = QPushButton("Validate Generated")
        self.validate_btn.clicked.connect(self._validate)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        for b in (self.generate_btn, self.validate_btn, self.stop_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        self.root.addLayout(btns)

        stats_row = QHBoxLayout()
        self.gen_card = StatCard("Generated")
        self.new_card = StatCard("Added to Queue")
        self.status_card = StatCard("Status", "Idle")
        for c in (self.gen_card, self.new_card, self.status_card):
            stats_row.addWidget(c)
        self.root.addLayout(stats_row)

        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(["Candidate", "Protocol", "Host", "Port"])
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.horizontalHeader().setStretchLastSection(True)
        self.root.addWidget(self.results, 1)

    def _config(self) -> dict:
        return {
            "name": f"internet:{self.profile_edit.text().strip() or 'default'}",
            "profile": self.profile_edit.text().strip() or "default",
            "cidrs": self.cidrs_edit.toPlainText(),
            "ports": self.ports_edit.text(),
            "max_candidates": self.max_spin.value(),
            "shuffle": True,
        }

    def _generate(self) -> None:
        cfg = self._config()
        # Validate config up front.
        provider = self.ctx.discovery.build("internet", cfg)
        ok, msg = provider.validate_configuration()
        if not ok:
            self.toast(msg, "warning")
            return
        self._control = JobControl()
        self.results.setRowCount(0)
        self._generated = 0
        worker = DiscoveryWorker(self.ctx, "internet", cfg, self._control)
        worker.item.connect(self._on_candidate)
        worker.progress.connect(lambda snap: self.status_card.set_value("Generating..."))
        worker.completed.connect(lambda out: self._done(out, worker))
        worker.failed.connect(lambda e: self.toast(f"Generation failed: {e}", "error"))
        self._workers.append(worker)
        self.stop_btn.setEnabled(True)
        self.status_card.set_value("Generating...")
        worker.start()

    def _on_candidate(self, cand) -> None:
        self._generated += 1
        self.gen_card.set_value(self._generated)
        if self.results.rowCount() < 2000:
            r = self.results.rowCount()
            self.results.insertRow(r)
            ep = cand.endpoint
            for c, v in enumerate([ep.identity, ep.protocol.value.upper(), ep.host, str(ep.port)]):
                self.results.setItem(r, c, QTableWidgetItem(str(v)))

    def _done(self, out: dict, worker) -> None:
        self.stop_btn.setEnabled(False)
        self.status_card.set_value("Complete")
        self.gen_card.set_value(out["found"])
        self.new_card.set_value(out["new"])
        self.toast(f"Generated {out['found']} candidate(s), {out['new']} queued", "success")
        if worker in self._workers:
            self._workers.remove(worker)

    def _validate(self) -> None:
        candidates = []
        with self.ctx.database.session() as session:
            for row in repo.list_discovery_results(session):
                candidates.append(repo.discovery_result_to_candidate(row, self.ctx.cipher))
        if not candidates:
            self.toast("No queued candidates. Generate first.", "warning")
            return
        worker = ValidationWorker(self.ctx, candidates, self.ctx.settings.get("testing", "default_profile", "quick"))
        worker.progress.connect(lambda s: self.status_card.set_value(f"{s.get('completed',0)}/{s.get('total',0)}"))
        worker.completed.connect(lambda res: self._validated(res, worker))
        worker.failed.connect(lambda e: self.toast(f"Validation failed: {e}", "error"))
        self._workers.append(worker)
        self.status_card.set_value("Validating...")
        worker.start()

    def _validated(self, res, worker) -> None:
        self.status_card.set_value("Validated")
        self.toast(f"Validated: {res.working} working / {res.total}", "success")
        with self.ctx.database.session() as session:
            repo.clear_discovery_results(session)
        if worker in self._workers:
            self._workers.remove(worker)
        self.main.notify_proxies_changed()

    def _stop(self) -> None:
        if self._control:
            self._control.stop()
            self.status_card.set_value("Stopping...")
