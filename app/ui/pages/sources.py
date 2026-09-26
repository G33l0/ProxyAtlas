"""Sources page: manage discovery sources (add/edit/enable/test/run)."""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.database import repository as repo
from app.testing.engine import JobControl
from app.ui.dialogs.source_dialog import SourceDialog
from app.ui.pages.base import BasePage
from app.ui.widgets.common import Card, EmptyState
from app.workers.discovery_worker import DiscoveryWorker


class SourcesPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Sources", "Configure where proxy candidates come from")
        self._workers: list = []

        toolbar = QHBoxLayout()
        for label, slot, primary in [
            ("Add Source", self._add, True), ("Edit", self._edit, False),
            ("Enable/Disable", self._toggle, False), ("Test", self._test, False),
            ("Run", self._run, False), ("Delete", self._delete, False), ("Refresh", self.refresh, False),
        ]:
            b = QPushButton(label)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(slot)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        self.root.addLayout(toolbar)

        self.stack = QStackedWidget()
        card = Card()
        cl = QVBoxLayout(card)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Name", "Provider", "Type", "Enabled", "Last Run", "Last Result"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit)
        cl.addWidget(self.table)
        self.stack.addWidget(card)
        self.empty = EmptyState("No discovery sources configured.")
        self.stack.addWidget(self.empty)
        self.root.addWidget(self.stack, 1)

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        with self.ctx.database.session() as session:
            self._sources = repo.list_sources(session)
            rows = [(s.id, s.name, s.provider, s.source_type, s.enabled,
                     s.last_run_at, s.last_status, s.last_count) for s in self._sources]
        self.table.setRowCount(len(rows))
        for i, (sid, name, provider, stype, enabled, last_run, last_status, last_count) in enumerate(rows):
            item = QTableWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, sid)
            self.table.setItem(i, 0, item)
            self.table.setItem(i, 1, QTableWidgetItem(provider))
            self.table.setItem(i, 2, QTableWidgetItem(stype))
            self.table.setItem(i, 3, QTableWidgetItem("Yes" if enabled else "No"))
            self.table.setItem(i, 4, QTableWidgetItem(last_run.strftime("%Y-%m-%d %H:%M") if last_run else "-"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{last_status or '-'} ({last_count})"))
        self.stack.setCurrentWidget(self.empty if not rows else self.stack.widget(0))

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        sid = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((s for s in self._sources if s.id == sid), None)

    def _add(self) -> None:
        dlg = SourceDialog(self)
        if dlg.exec() != SourceDialog.DialogCode.Accepted:
            return
        data = dlg.result_data()
        with self.ctx.database.session() as session:
            repo.upsert_source(session, data["name"], data["source_type"], data["provider"], data["config"], data["enabled"])
        self.toast("Source added", "success")
        self.refresh()

    def _edit(self) -> None:
        src = self._selected()
        if src is None:
            self.toast("Select a source", "warning")
            return
        existing = {
            "name": src.name, "provider": src.provider,
            "config": json.loads(src.config_json or "{}"), "enabled": src.enabled,
        }
        dlg = SourceDialog(self, existing=existing)
        if dlg.exec() != SourceDialog.DialogCode.Accepted:
            return
        data = dlg.result_data()
        with self.ctx.database.session() as session:
            repo.upsert_source(session, data["name"], data["source_type"], data["provider"], data["config"], data["enabled"], source_id=src.id)
        self.toast("Source updated", "success")
        self.refresh()

    def _toggle(self) -> None:
        src = self._selected()
        if src is None:
            return
        with self.ctx.database.session() as session:
            fresh = repo.get_source(session, src.id)
            repo.upsert_source(session, fresh.name, fresh.source_type, fresh.provider,
                               json.loads(fresh.config_json or "{}"), not fresh.enabled, source_id=fresh.id)
        self.refresh()

    def _test(self) -> None:
        src = self._selected()
        if src is None:
            return
        try:
            provider = self.ctx.discovery.build(src.provider, json.loads(src.config_json or "{}"))
            ok, msg = provider.validate_configuration()
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, str(exc)
        self.toast(f"{'OK' if ok else 'Invalid'}: {msg}", "success" if ok else "error")

    def _run(self) -> None:
        src = self._selected()
        if src is None:
            return
        config = json.loads(src.config_json or "{}")
        worker = DiscoveryWorker(self.ctx, src.provider, config, JobControl())
        worker.completed.connect(lambda out: self._run_done(out, src.id, worker))
        worker.failed.connect(lambda e: self._run_failed(e, src.id, worker))
        self._workers.append(worker)
        self.toast(f"Running source '{src.name}'...", "info")
        worker.start()

    def _run_done(self, out, sid, worker) -> None:
        with self.ctx.database.session() as session:
            src = repo.get_source(session, sid)
            if src:
                from datetime import datetime, timezone

                src.last_run_at = datetime.now(timezone.utc)
                src.last_status = "ok" if not out.get("errors") else "warning"
                src.last_count = out["new"]
                src.last_error = "; ".join(out.get("errors", [])) or None
        self.toast(f"Source run: {out['new']} new candidate(s)", "success")
        if worker in self._workers:
            self._workers.remove(worker)
        self.refresh()

    def _run_failed(self, err, sid, worker) -> None:
        with self.ctx.database.session() as session:
            src = repo.get_source(session, sid)
            if src:
                src.last_status = "error"
                src.last_error = err
        self.toast(f"Source failed: {err}", "error")
        if worker in self._workers:
            self._workers.remove(worker)
        self.refresh()

    def _delete(self) -> None:
        src = self._selected()
        if src is None:
            return
        if QMessageBox.question(self, "Delete", f"Delete source '{src.name}'?") != QMessageBox.StandardButton.Yes:
            return
        with self.ctx.database.session() as session:
            repo.delete_source(session, src.id)
        self.refresh()
