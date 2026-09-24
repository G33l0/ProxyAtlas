"""Proxies page: filterable, paginated results table with actions."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
)

from app.core.enums import Protocol
from app.core.models import Endpoint, ProxyCandidate
from app.database import repository as repo
from app.database.filters import FilterSpec
from app.ui.dialogs.export_dialog import ExportDialog
from app.ui.dialogs.proxy_details import ProxyDetailsDialog
from app.ui.models.proxy_table_model import COLUMNS, ProxyTableModel
from app.ui.pages.base import BasePage
from app.ui.widgets.common import Card, EmptyState, Row
from app.ui.widgets.filter_bar import FilterBar
from app.workers.export_worker import ExportWorker
from app.workers.validation_worker import ValidationWorker

QUICK_FILTERS = [
    ("All", FilterSpec()),
    ("Working", FilterSpec().add("status", "eq", "working")),
    ("Failed", FilterSpec().add("status", "eq", "failed")),
    ("Residential", FilterSpec().add("classification", "eq", "residential")),
    ("Mobile", FilterSpec().add("classification", "eq", "mobile")),
    ("Datacenter", FilterSpec().add("classification", "eq", "datacenter")),
    ("ISP", FilterSpec().add("classification", "eq", "isp")),
    ("Business", FilterSpec().add("classification", "eq", "business")),
    ("Educational", FilterSpec().add("classification", "eq", "educational")),
    ("Government", FilterSpec().add("classification", "eq", "government")),
    ("Unknown", FilterSpec().add("classification", "eq", "unknown")),
]


class ProxiesPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Proxies", "Search, filter and manage your validated proxy database")
        self._spec = FilterSpec()
        self._page = 0
        self._page_size = int(ctx.settings.get("general", "results_page_size", 200))
        self._sort_by = "score"
        self._descending = True
        self._total = 0
        self._workers: list = []

        # Quick filter chips.
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        self._chip_buttons: list[QPushButton] = []
        for label, spec in QUICK_FILTERS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c, s=spec, b=None: self._apply_quick(s))
            chip_row.addWidget(btn)
            self._chip_buttons.append(btn)
        chip_row.addStretch(1)
        self._chip_buttons[0].setChecked(True)
        self.root.addLayout(chip_row)

        # Advanced filter bar.
        self.filter_bar = FilterBar()
        self.filter_bar.applied.connect(self._on_filter_applied)
        self.filter_bar.cleared.connect(self._on_filter_cleared)
        self.filter_bar.save_requested.connect(self._save_filter)
        self.filter_bar.load_requested.connect(self._load_filter)
        filter_card = Card()
        from PyQt6.QtWidgets import QVBoxLayout

        fc_layout = QVBoxLayout(filter_card)
        fc_layout.addWidget(self.filter_bar)
        self.root.addWidget(filter_card)

        # Table / empty state stack.
        self.stack = QStackedWidget()
        self.model = ProxyTableModel(self.palette_)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda idx: self._show_details(self.model.proxy_id(idx.row())))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_column)
        self.table.setColumnWidth(1, 130)
        self.stack.addWidget(self.table)
        self.empty = EmptyState("No validated proxies yet.\nRun discovery or import a proxy list to begin.")
        self.stack.addWidget(self.empty)
        self.root.addWidget(self.stack, 1)

        # Footer: pagination + actions.
        footer = QHBoxLayout()
        self.count_label = QLabel("0 proxies")
        self.count_label.setObjectName("StatLabel")
        self.prev_btn = QPushButton("‹ Prev")
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn = QPushButton("Next ›")
        self.next_btn.clicked.connect(self._next_page)
        self.page_label = QLabel("Page 1")
        self.page_label.setObjectName("StatLabel")

        retest_btn = QPushButton("Re-test Selected")
        retest_btn.clicked.connect(self._retest_selected)
        export_btn = QPushButton("Export")
        export_btn.setObjectName("Primary")
        export_btn.clicked.connect(self._export)

        footer.addWidget(self.count_label)
        footer.addStretch(1)
        footer.addWidget(retest_btn)
        footer.addWidget(export_btn)
        footer.addSpacing(12)
        footer.addWidget(self.prev_btn)
        footer.addWidget(self.page_label)
        footer.addWidget(self.next_btn)
        self.root.addWidget(Row())  # spacer
        self.root.addLayout(footer)

    # --- data ---------------------------------------------------------------
    def refresh(self) -> None:
        with self.ctx.database.session() as session:
            self._total = repo.count_proxies(session, self._spec)
            max_page = max(0, (self._total - 1) // self._page_size)
            self._page = min(self._page, max_page)
            rows = repo.query_proxies(
                session, self._spec, sort_by=self._sort_by, descending=self._descending,
                limit=self._page_size, offset=self._page * self._page_size,
            )
            from app.ui.models.proxy_table_model import proxy_to_dict

            data = [proxy_to_dict(p) for p in rows]
        self.model.set_palette(self.palette_)
        self.model.set_rows(data)
        self.stack.setCurrentWidget(self.table if (data or self._total) else self.empty)
        if self._total == 0 and self._has_active_filter():
            self.empty.set_message("No working proxies match the current filters.")
            self.stack.setCurrentWidget(self.empty)
        elif self._total == 0:
            self.empty.set_message("No validated proxies yet.\nRun discovery or import a proxy list to begin.")
            self.stack.setCurrentWidget(self.empty)
        self.count_label.setText(f"{self._total} proxies")
        pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        self.page_label.setText(f"Page {self._page + 1} / {pages}")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < pages - 1)

    def _has_active_filter(self) -> bool:
        return bool(self._spec.conditions or self._spec.search)

    # --- events -------------------------------------------------------------
    def on_shown(self) -> None:
        self.refresh()

    def on_theme_changed(self) -> None:
        self.model.set_palette(self.palette_)

    def on_proxies_changed(self) -> None:
        self.refresh()

    def focus_search(self) -> None:
        self.filter_bar.search.setFocus()
        self.filter_bar.search.selectAll()

    def _apply_quick(self, spec: FilterSpec) -> None:
        sender = self.sender()
        for b in self._chip_buttons:
            b.setChecked(b is sender)
        self._spec = FilterSpec.from_dict(spec.to_dict())
        self._page = 0
        self.refresh()

    def _on_filter_applied(self, spec: FilterSpec) -> None:
        for b in self._chip_buttons:
            b.setChecked(False)
        self._spec = spec
        self._page = 0
        self.refresh()

    def _on_filter_cleared(self) -> None:
        self._spec = FilterSpec()
        self._chip_buttons[0].setChecked(True)
        self._page = 0
        self.refresh()

    def _sort_by_column(self, section: int) -> None:
        if not (0 <= section < len(COLUMNS)):
            return
        key = COLUMNS[section][2]
        if key == self._sort_by:
            self._descending = not self._descending
        else:
            self._sort_by = key
            self._descending = True
        self.refresh()

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self.refresh()

    def _next_page(self) -> None:
        self._page += 1
        self.refresh()

    # --- selection helpers --------------------------------------------------
    def _selected_ids(self) -> list[int]:
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        return [pid for r in sorted(rows) if (pid := self.model.proxy_id(r)) is not None]

    def _selected_rows(self) -> list[dict]:
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        return [d for r in sorted(rows) if (d := self.model.row_dict(r)) is not None]

    def _context_menu(self, pos) -> None:
        if not self.table.selectionModel().hasSelection():
            return
        menu = QMenu(self)
        act_details = QAction("View Details", self)
        act_details.triggered.connect(lambda: self._show_details(self._selected_ids()[0]))
        act_copy = QAction("Copy Endpoint(s)", self)
        act_copy.triggered.connect(self._copy_endpoints)
        act_retest = QAction("Re-test Selected", self)
        act_retest.triggered.connect(self._retest_selected)
        act_tag = QAction("Add Tag…", self)
        act_tag.triggered.connect(self._add_tag)
        act_export = QAction("Export Selected…", self)
        act_export.triggered.connect(lambda: self._export(selected_only=True))
        act_delete = QAction("Delete Selected", self)
        act_delete.triggered.connect(self._delete_selected)
        for a in (act_details, act_copy, act_retest, act_tag, act_export):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_delete)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _show_details(self, proxy_id: int | None) -> None:
        if proxy_id is None:
            return
        dlg = ProxyDetailsDialog(self.ctx, self.palette_, proxy_id, self)
        dlg.exec()

    def _copy_endpoints(self) -> None:
        rows = self._selected_rows()
        lines = [f"{r['protocol']}://{r['host']}:{r['port']}" for r in rows]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.toast(f"Copied {len(lines)} endpoint(s)", "success")

    def _add_tag(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        tag, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")
        if ok and tag.strip():
            with self.ctx.database.session() as session:
                for pid in ids:
                    repo.add_tag(session, pid, tag.strip())
            self.toast(f"Tagged {len(ids)} prox, '{tag.strip()}'", "success")
            self.refresh()

    def _delete_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        if self.ctx.settings.get("general", "confirm_destructive", True):
            reply = QMessageBox.question(
                self, "Delete Proxies", f"Delete {len(ids)} selected prox{'y' if len(ids)==1 else 'ies'}?"
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        with self.ctx.database.session() as session:
            deleted = repo.delete_proxies(session, ids)
        self.toast(f"Deleted {deleted} prox{'y' if deleted==1 else 'ies'}", "info")
        self.main.notify_proxies_changed()

    def _retest_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self.toast("Select proxies to re-test", "warning")
            return
        candidates = []
        with self.ctx.database.session() as session:
            for r in rows:
                proxy = repo.get_proxy(session, r["id"])
                if proxy is None:
                    continue
                user, pw = repo.get_credentials(session, proxy, self.ctx.cipher)
                ep = Endpoint(proxy.host, proxy.port, Protocol.from_value(proxy.protocol, Protocol.HTTP), user, pw)
                candidates.append(ProxyCandidate(ep, source=proxy.source))
        if not candidates:
            return
        worker = ValidationWorker(self.ctx, candidates, self.ctx.settings.get("testing", "default_profile", "standard"))
        worker.completed.connect(lambda res: self._retest_done(res, worker))
        worker.failed.connect(lambda e: self.toast(f"Re-test failed: {e}", "error"))
        self._workers.append(worker)
        worker.start()
        self.toast(f"Re-testing {len(candidates)} prox{'y' if len(candidates)==1 else 'ies'}…", "info")

    def _retest_done(self, res, worker) -> None:
        self.toast(f"Re-test complete: {res.working} working / {res.total}", "success")
        if worker in self._workers:
            self._workers.remove(worker)
        self.main.notify_proxies_changed()

    # --- export -------------------------------------------------------------
    def _export(self, selected_only: bool = False) -> None:
        if selected_only and not self._selected_ids():
            self.toast("No rows selected", "warning")
            return
        dlg = ExportDialog(self, default_dir=str(self.ctx.paths.exports_dir))
        if dlg.exec() != ExportDialog.DialogCode.Accepted:
            return
        opts = dlg.options()
        if not opts["path"]:
            self.toast("Choose an output file", "warning")
            return
        if selected_only:
            # Selected-row export writes the chosen rows directly.
            self._export_selected_rows(opts)
            return
        worker = ExportWorker(
            self.ctx, self._spec, opts["path"], opts["fmt"],
            working_only=opts["working_only"], txt_format=opts["txt_format"],
        )
        worker.completed.connect(lambda info: self._export_done(info, worker))
        worker.failed.connect(lambda e: self.toast(f"Export failed: {e}", "error"))
        self._workers.append(worker)
        worker.start()
        self.toast("Exporting…", "info")

    def _export_selected_rows(self, opts: dict) -> None:
        from app.services.exporters import export_rows, proxy_to_row

        rows = self._selected_rows()
        with self.ctx.database.session() as session:
            full = []
            for r in rows:
                p = repo.get_proxy(session, r["id"])
                if p:
                    full.append(proxy_to_row(p))
        try:
            count = export_rows(full, opts["path"], opts["fmt"], opts["working_only"], opts["txt_format"])
            self.toast(f"Exported {count} proxies to {opts['path']}", "success")
        except Exception as exc:  # noqa: BLE001
            self.toast(f"Export failed: {exc}", "error")

    def _export_done(self, info: dict, worker) -> None:
        self.toast(f"Exported {info['count']} proxies → {info['path']}", "success")
        if worker in self._workers:
            self._workers.remove(worker)

    # --- saved filters ------------------------------------------------------
    def _save_filter(self, spec: FilterSpec) -> None:
        name, ok = QInputDialog.getText(self, "Save Filter", "Filter name:")
        if ok and name.strip():
            with self.ctx.database.session() as session:
                repo.save_filter(session, name.strip(), spec)
            self.toast(f"Saved filter '{name.strip()}'", "success")

    def _load_filter(self) -> None:
        with self.ctx.database.session() as session:
            filters = repo.list_saved_filters(session)
        if not filters:
            self.toast("No saved filters", "warning")
            return
        names = [f["name"] for f in filters]
        name, ok = QInputDialog.getItem(self, "Load Filter", "Select filter:", names, 0, False)
        if ok and name:
            spec_dict = next((f["filter"] for f in filters if f["name"] == name), None)
            if spec_dict:
                self.filter_bar.load_spec(FilterSpec.from_dict(spec_dict))
