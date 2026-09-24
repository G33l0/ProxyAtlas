"""Reports page: generate reports and view recent exports."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from app.database.filters import FilterSpec
from app.database.models import ExportJob
from app.ui.dialogs.export_dialog import ExportDialog
from app.ui.pages.base import BasePage
from app.ui.pages.proxies import QUICK_FILTERS
from app.ui.widgets.common import Card
from app.workers.export_worker import ExportWorker


class ReportsPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Reports", "Generate professional reports and exports")
        self._workers: list = []

        controls = Card()
        cl = QHBoxLayout(controls)
        cl.addWidget(QLabel("Dataset:"))
        self.filter_combo = QComboBox()
        for label, spec in QUICK_FILTERS:
            self.filter_combo.addItem(label, spec)
        cl.addWidget(self.filter_combo)
        report_btn = QPushButton("Generate Report…")
        report_btn.setObjectName("Primary")
        report_btn.clicked.connect(lambda: self._generate(as_report=True))
        export_btn = QPushButton("Export Data…")
        export_btn.clicked.connect(lambda: self._generate(as_report=False))
        cl.addWidget(report_btn)
        cl.addWidget(export_btn)
        cl.addStretch(1)
        self.root.addWidget(controls)

        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["When", "Format", "Records", "Path"])
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.horizontalHeader().setStretchLastSection(True)
        self.root.addWidget(self.history, 1)

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        from sqlalchemy import select

        with self.ctx.database.session() as session:
            jobs = list(session.scalars(select(ExportJob).order_by(ExportJob.created_at.desc()).limit(50)).all())
            rows = [(j.created_at, j.fmt, j.record_count, j.path) for j in jobs]
        self.history.setRowCount(len(rows))
        for i, (when, fmt, count, path) in enumerate(rows):
            self.history.setItem(i, 0, QTableWidgetItem(when.strftime("%Y-%m-%d %H:%M") if when else ""))
            self.history.setItem(i, 1, QTableWidgetItem(str(fmt).upper()))
            self.history.setItem(i, 2, QTableWidgetItem(str(count)))
            self.history.setItem(i, 3, QTableWidgetItem(str(path)))

    def _generate(self, as_report: bool) -> None:
        base = self.filter_combo.currentData()
        spec = FilterSpec.from_dict(base.to_dict())
        dlg = ExportDialog(self, default_dir=str(self.ctx.paths.reports_dir if as_report else self.ctx.paths.exports_dir), as_report=as_report)
        if dlg.exec() != ExportDialog.DialogCode.Accepted:
            return
        opts = dlg.options()
        if not opts["path"]:
            self.toast("Choose an output file", "warning")
            return
        worker = ExportWorker(
            self.ctx, spec, opts["path"], opts["fmt"],
            working_only=opts["working_only"], txt_format=opts["txt_format"], as_report=as_report,
        )
        worker.completed.connect(lambda info: self._done(info, worker))
        worker.failed.connect(lambda e: self.toast(f"Generation failed: {e}", "error"))
        self._workers.append(worker)
        self.toast("Generating…", "info")
        worker.start()

    def _done(self, info: dict, worker) -> None:
        self.toast(f"Wrote {info['count']} records → {info['path']}", "success")
        if worker in self._workers:
            self._workers.remove(worker)
        self.refresh()
