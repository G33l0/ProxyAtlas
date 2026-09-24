"""Monitoring page: monitored collections/filters with history charts."""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
)

from app.database import repository as repo
from app.ui.pages.base import BasePage
from app.ui.widgets.charts import LineChart
from app.ui.widgets.common import Card, EmptyState
from app.workers.monitoring_worker import MonitoringWorker


class MonitorJobDialog(QDialog):
    def __init__(self, parent, collections: list[str], existing=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Monitoring Job")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.name = QLineEdit(existing.name if existing else "")
        self.target = QComboBox()
        self.target.addItem("All working proxies", ("filter", json.dumps({"conditions": [{"field": "status", "op": "eq", "value": "working"}], "combine": "and", "search": None})))
        for c in collections:
            self.target.addItem(f"Collection: {c}", ("collection_name", c))
        self.interval = QSpinBox()
        self.interval.setRange(1, 10080)
        self.interval.setValue(existing.interval_minutes if existing else 30)
        form.addRow("Name", self.name)
        form.addRow("Target", self.target)
        form.addRow("Interval (minutes)", self.interval)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class MonitoringPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Monitoring", "Track availability and latency over time")
        self._workers: list = []

        toolbar = QHBoxLayout()
        for label, slot, primary in [
            ("New Monitor", self._new, True), ("Run Now", self._run_now, False),
            ("Delete", self._delete, False), ("Refresh", self.refresh, False),
        ]:
            b = QPushButton(label)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(slot)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        self.root.addLayout(toolbar)

        self.stack = QStackedWidget()
        body = Card()
        bl = QHBoxLayout(body)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "Target", "Interval", "Last Run", "Last Result"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update_chart)
        bl.addWidget(self.table, 2)
        self.chart = LineChart(self.palette_, "Working proxies over time")
        bl.addWidget(self.chart, 1)
        self.stack.addWidget(body)
        self.empty = EmptyState("No monitoring collections configured.")
        self.stack.addWidget(self.empty)
        self.root.addWidget(self.stack, 1)

    def on_shown(self) -> None:
        self.refresh()

    def on_theme_changed(self) -> None:
        self.chart.set_palette(self.palette_)

    def refresh(self) -> None:
        with self.ctx.database.session() as session:
            self._jobs = repo.list_monitoring_jobs(session)
            rows = []
            for j in self._jobs:
                history = repo.monitoring_history(session, j.id, limit=1)
                last = history[-1] if history else None
                rows.append((j, last))
        self.table.setRowCount(len(rows))
        for i, (j, last) in enumerate(rows):
            self.table.setItem(i, 0, self._item(j.name, j.id))
            self.table.setItem(i, 1, QTableWidgetItem(j.target_type))
            self.table.setItem(i, 2, QTableWidgetItem(f"{j.interval_minutes} min"))
            self.table.setItem(i, 3, QTableWidgetItem(j.last_run_at.strftime("%Y-%m-%d %H:%M") if j.last_run_at else "—"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{last.working}/{last.total} working" if last else "—"))
        self.stack.setCurrentWidget(self.empty if not rows else self.stack.widget(0))

    def _item(self, text, jid):
        it = QTableWidgetItem(text)
        it.setData(Qt.ItemDataRole.UserRole, jid)
        return it

    def _selected_job_id(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def _update_chart(self) -> None:
        jid = self._selected_job_id()
        if jid is None:
            return
        with self.ctx.database.session() as session:
            history = repo.monitoring_history(session, jid, limit=100)
        self.chart.set_series([h.working for h in history])

    def _new(self) -> None:
        with self.ctx.database.session() as session:
            collections = [c["name"] for c in repo.list_collections(session)]
        dlg = MonitorJobDialog(self, collections)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        kind, ref = dlg.target.currentData()
        target_type = "filter"
        target_ref = ref
        if kind == "collection_name":
            with self.ctx.database.session() as session:
                col = next((c for c in repo.list_collections(session) if c["name"] == ref), None)
            target_type = "filter"
            target_ref = json.dumps(col["filter"]) if col else json.dumps({"conditions": [], "combine": "and", "search": None})
        with self.ctx.database.session() as session:
            repo.upsert_monitoring_job(session, dlg.name.text().strip() or "Monitor", target_type, target_ref, dlg.interval.value())
        self.toast("Monitoring job created", "success")
        self.refresh()

    def _run_now(self) -> None:
        jid = self._selected_job_id()
        if jid is None:
            self.toast("Select a monitoring job", "warning")
            return
        with self.ctx.database.session() as session:
            job = next((j for j in repo.list_monitoring_jobs(session) if j.id == jid), None)
        if job is None:
            return
        worker = MonitoringWorker(self.ctx, job.id, job.target_type, job.target_ref or "")
        worker.completed.connect(lambda out: self._run_done(out, worker))
        worker.failed.connect(lambda e: self.toast(f"Monitor failed: {e}", "error"))
        self._workers.append(worker)
        self.toast("Running monitor…", "info")
        worker.start()

    def _run_done(self, outcome, worker) -> None:
        self.toast(f"Monitor: {outcome.working}/{outcome.total} working", "success")
        if worker in self._workers:
            self._workers.remove(worker)
        self.refresh()
        self._update_chart()

    def _delete(self) -> None:
        jid = self._selected_job_id()
        if jid is None:
            return
        if QMessageBox.question(self, "Delete", "Delete selected monitoring job?") != QMessageBox.StandardButton.Yes:
            return
        with self.ctx.database.session() as session:
            repo.delete_monitoring_job(session, jid)
        self.refresh()
