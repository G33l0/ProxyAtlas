"""Export and report workers — run file generation off the GUI thread."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from app.database import repository as repo
from app.database.filters import FilterSpec
from app.reports.generator import write_report
from app.services.app_context import AppContext
from app.services.exporters import export_rows, proxy_to_row


class ExportWorker(QThread):
    """Query proxies matching a filter and write them to a file."""

    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        ctx: AppContext,
        spec: FilterSpec,
        path: str,
        fmt: str,
        working_only: bool = False,
        txt_format: str = "ip_port",
        as_report: bool = False,
        include_credentials: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.spec = spec
        self.path = path
        self.fmt = fmt
        self.working_only = working_only
        self.txt_format = txt_format
        self.as_report = as_report
        self.include_credentials = include_credentials

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            with self.ctx.database.session() as session:
                proxies = repo.query_proxies(session, self.spec, limit=100000)
                cipher = self.ctx.cipher if self.include_credentials else None
                rows: list[dict[str, Any]] = [
                    proxy_to_row(p, cipher, self.include_credentials) for p in proxies
                ]
                if self.as_report:
                    count = write_report(rows, self.path, self.fmt, "ProxyAtlas Report")
                else:
                    count = export_rows(
                        rows, self.path, self.fmt, self.working_only, self.txt_format
                    )
                repo.record_export(
                    session, self.fmt, str(self.path), count, self.spec_to_json()
                )
            self.completed.emit({"path": str(Path(self.path)), "count": count, "fmt": self.fmt})
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def spec_to_json(self) -> str:
        import json

        return json.dumps(self.spec.to_dict())
