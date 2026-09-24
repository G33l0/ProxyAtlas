"""Discovery page: sources, discovery jobs, live results, validation queue."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.database import repository as repo
from app.discovery.importer import ProxyImporter
from app.testing.engine import JobControl
from app.ui.pages.base import BasePage
from app.ui.widgets.common import Card
from app.workers.discovery_worker import DiscoveryWorker
from app.workers.validation_worker import ValidationWorker

QUEUE_HEADERS = ["Candidate", "Protocol", "Host", "Port", "Source", "Discovered", "Status"]


class DiscoveryPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Discovery", "Collect proxy candidates and feed the validation pipeline")
        self._workers: list = []
        self._control: JobControl | None = None

        # Controls card.
        controls = Card()
        cl = QHBoxLayout(controls)
        self.source_combo = QComboBox()
        cl.addWidget(QLabel("Source:"))
        cl.addWidget(self.source_combo, 1)
        run_btn = QPushButton("Run Source")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self._run_source)
        import_btn = QPushButton("Import File…")
        import_btn.clicked.connect(self._import_file)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        manage_btn = QPushButton("Manage Sources")
        manage_btn.clicked.connect(lambda: self.main.navigate("sources"))
        for b in (run_btn, import_btn, self.stop_btn, manage_btn):
            cl.addWidget(b)
        self.root.addWidget(controls)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("StatLabel")
        self.root.addWidget(self.status_label)

        # Tabs: validation queue + live results.
        self.tabs = QTabWidget()
        self.queue_table = self._make_table()
        self.live_table = self._make_table()
        self.tabs.addTab(self._queue_tab(), "Validation Queue")
        self.tabs.addTab(self.live_table, "Live Results")
        self.root.addWidget(self.tabs, 1)

    def _make_table(self) -> QTableWidget:
        t = QTableWidget(0, len(QUEUE_HEADERS))
        t.setHorizontalHeaderLabels(QUEUE_HEADERS)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        t.horizontalHeader().setStretchLastSection(True)
        return t

    def _queue_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        for label, slot in [
            ("Validate Selected", self._validate_selected),
            ("Validate All", self._validate_all),
            ("Delete", self._delete_selected),
            ("Export", self._export_queue),
            ("Clear", self._clear_queue),
            ("Refresh", self.refresh),
        ]:
            btn = QPushButton(label)
            if label == "Validate All":
                btn.setObjectName("Primary")
            btn.clicked.connect(slot)
            actions.addWidget(btn)
        actions.addStretch(1)
        self.queue_count = QLabel("0 candidates")
        self.queue_count.setObjectName("StatLabel")
        actions.addWidget(self.queue_count)
        layout.addLayout(actions)
        layout.addWidget(self.queue_table, 1)
        return w

    # --- data ---------------------------------------------------------------
    def on_shown(self) -> None:
        self._reload_sources()
        self.refresh()

    def _reload_sources(self) -> None:
        self.source_combo.clear()
        with self.ctx.database.session() as session:
            self._sources = repo.list_sources(session)
            for s in self._sources:
                label = f"{s.name} [{s.provider}]" + ("" if s.enabled else " (disabled)")
                self.source_combo.addItem(label, s.id)

    def refresh(self) -> None:
        with self.ctx.database.session() as session:
            rows = repo.list_discovery_results(session, limit=5000)
            data = [(r.id, r.protocol, r.host, r.port, r.source, r.discovered_at, r.validation_status) for r in rows]
        self._fill_table(self.queue_table, data)
        self.queue_count.setText(f"{len(data)} candidates")

    def _fill_table(self, table: QTableWidget, rows: list) -> None:
        table.setRowCount(len(rows))
        for i, (rid, proto, host, port, source, discovered, status) in enumerate(rows):
            endpoint = f"{proto}://{host}:{port}"
            values = [endpoint, str(proto).upper(), host, str(port), source,
                      discovered.strftime("%H:%M:%S") if discovered else "", status]
            for c, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, rid)
                table.setItem(i, c, item)

    # --- discovery run ------------------------------------------------------
    def _run_source(self) -> None:
        sid = self.source_combo.currentData()
        if sid is None:
            self.toast("No source selected. Add one under Sources.", "warning")
            return
        with self.ctx.database.session() as session:
            src = repo.get_source(session, sid)
            if src is None:
                return
            import json
            config = json.loads(src.config_json or "{}")
            provider = src.provider
        self._control = JobControl()
        self.live_table.setRowCount(0)
        self._live_rows: list = []
        worker = DiscoveryWorker(self.ctx, provider, config, self._control)
        worker.item.connect(self._on_candidate)
        worker.progress.connect(lambda snap: self.status_label.setText(
            f"Discovering… found {snap.get('found', 0)}"))
        worker.completed.connect(lambda out: self._discovery_done(out, worker))
        worker.failed.connect(lambda e: self._discovery_failed(e, worker))
        self._workers.append(worker)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("Discovering…")
        self.tabs.setCurrentIndex(1)
        worker.start()

    def _on_candidate(self, cand) -> None:
        self._live_rows.append(cand)
        if len(self._live_rows) <= 2000:
            r = self.live_table.rowCount()
            self.live_table.insertRow(r)
            ep = cand.endpoint
            values = [ep.identity, ep.protocol.value.upper(), ep.host, str(ep.port),
                      cand.source, cand.discovered_at.strftime("%H:%M:%S"), cand.validation_status.value]
            for c, v in enumerate(values):
                self.live_table.setItem(r, c, QTableWidgetItem(str(v)))

    def _discovery_done(self, out: dict, worker) -> None:
        self.stop_btn.setEnabled(False)
        self.status_label.setText(f"Discovery complete: {out['found']} found, {out['new']} new")
        self.toast(f"Discovery: {out['new']} new candidate(s)", "success")
        if out.get("errors"):
            self.toast(f"Discovery warnings: {out['errors'][0]}", "warning")
        if worker in self._workers:
            self._workers.remove(worker)
        self.refresh()
        if self.ctx.settings.get("discovery", "auto_validate_after_discovery", False):
            self._validate_all()

    def _discovery_failed(self, err: str, worker) -> None:
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Discovery failed")
        self.toast(f"Discovery failed: {err}", "error")
        if worker in self._workers:
            self._workers.remove(worker)

    def _stop(self) -> None:
        if self._control:
            self._control.stop()
            self.status_label.setText("Stopping…")

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import proxy list", "", "Proxy lists (*.txt *.csv *.json);;All files (*)"
        )
        if not path:
            return
        importer = ProxyImporter()
        try:
            candidates, errors = importer.import_file(path)
        except Exception as exc:  # noqa: BLE001
            self.toast(f"Import failed: {exc}", "error")
            return
        new = 0
        with self.ctx.database.session() as session:
            for cand in candidates:
                _, is_new = repo.add_discovery_candidate(session, cand, self.ctx.cipher)
                new += int(is_new)
        self.toast(f"Imported {new} new candidate(s), {len(errors)} skipped", "success")
        self.refresh()

    # --- queue actions ------------------------------------------------------
    def _selected_queue_ids(self) -> list[int]:
        ids = []
        for idx in self.queue_table.selectionModel().selectedRows():
            item = self.queue_table.item(idx.row(), 0)
            if item is not None:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _validate_selected(self) -> None:
        ids = self._selected_queue_ids()
        if not ids:
            self.toast("Select candidates to validate", "warning")
            return
        self._validate_ids(ids)

    def _validate_all(self) -> None:
        with self.ctx.database.session() as session:
            ids = [r.id for r in repo.list_discovery_results(session)]
        if not ids:
            self.toast("Queue is empty", "warning")
            return
        self._validate_ids(ids)

    def _validate_ids(self, ids: list[int]) -> None:
        candidates = []
        with self.ctx.database.session() as session:
            for rid in ids:
                rows = [r for r in repo.list_discovery_results(session) if r.id == rid]
                for row in rows:
                    candidates.append(repo.discovery_result_to_candidate(row, self.ctx.cipher))
                    repo.update_discovery_status(session, rid, "testing")
        if not candidates:
            return
        profile = self.ctx.settings.get("testing", "default_profile", "standard")
        worker = ValidationWorker(self.ctx, candidates, profile)
        worker.progress.connect(lambda snap: self.status_label.setText(
            f"Validating… {snap.get('completed',0)}/{snap.get('total',0)} · {snap.get('working',0)} working"))
        worker.completed.connect(lambda res: self._validation_done(res, ids, worker))
        worker.failed.connect(lambda e: self.toast(f"Validation failed: {e}", "error"))
        self._workers.append(worker)
        self.status_label.setText(f"Validating {len(candidates)} candidate(s)…")
        worker.start()

    def _validation_done(self, res, ids, worker) -> None:
        # Update queue statuses and remove validated candidates.
        with self.ctx.database.session() as session:
            repo.delete_discovery_results(session, ids)
        self.status_label.setText(f"Validation complete: {res.working} working / {res.total}")
        self.toast(f"Validated: {res.working} working, {res.failed} failed", "success")
        if worker in self._workers:
            self._workers.remove(worker)
        self.refresh()
        self.main.notify_proxies_changed()

    def _delete_selected(self) -> None:
        ids = self._selected_queue_ids()
        if not ids:
            return
        with self.ctx.database.session() as session:
            repo.delete_discovery_results(session, ids)
        self.refresh()

    def _clear_queue(self) -> None:
        reply = QMessageBox.question(self, "Clear Queue", "Remove all candidates from the discovery queue?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        with self.ctx.database.session() as session:
            repo.clear_discovery_results(session)
        self.refresh()

    def _export_queue(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export queue", str(self.ctx.paths.exports_dir / "discovery_queue.txt"),
            "Text (*.txt)"
        )
        if not path:
            return
        with self.ctx.database.session() as session:
            rows = repo.list_discovery_results(session)
            lines = [f"{r.protocol}://{r.host}:{r.port}" for r in rows]
        from pathlib import Path

        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.toast(f"Exported {len(lines)} candidate(s)", "success")
