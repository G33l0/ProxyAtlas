"""Detailed proxy profile dialog."""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.enums import CLASSIFICATION_LABELS, STATUS_LABELS, Classification, ValidationStatus
from app.database import repository as repo
from app.services.app_context import AppContext
from app.ui.theme import Palette
from app.ui.widgets.charts import LineChart


class ProxyDetailsDialog(QDialog):
    def __init__(self, ctx: AppContext, palette: Palette, proxy_id: int, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.palette_ = palette
        self.proxy_id = proxy_id
        self.setWindowTitle("Proxy Details")
        self.setMinimumSize(640, 560)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._load()

    def _load(self) -> None:
        with self.ctx.database.session() as session:
            proxy = repo.get_proxy(session, self.proxy_id)
            if proxy is None:
                self.tabs.addTab(QLabel("Proxy not found"), "Details")
                return
            data = {c.name: getattr(proxy, c.name) for c in proxy.__table__.columns}
            score_components = proxy.score_components
            classification_evidence = proxy.classification_evidence
            history = repo.proxy_history(session, self.proxy_id, limit=100)
            tests = repo.proxy_tests(session, self.proxy_id, limit=30)
            latencies = [h.latency for h in history if h.latency is not None]

        self.tabs.addTab(self._overview_tab(data), "Overview")
        self.tabs.addTab(self._quality_tab(score_components, classification_evidence), "Quality & Classification")
        self.tabs.addTab(self._history_tab(latencies), "History")
        self.tabs.addTab(self._tests_tab(tests), "Tests")

    def _overview_tab(self, data: dict) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        def add(label: str, value) -> None:
            form.addRow(label, QLabel("—" if value in (None, "") else str(value)))

        status = STATUS_LABELS.get(ValidationStatus.from_value(data.get("status"), ValidationStatus.UNKNOWN), data.get("status"))
        cls = CLASSIFICATION_LABELS.get(Classification.from_value(data.get("classification"), Classification.UNKNOWN), data.get("classification"))
        add("Endpoint", f"{data.get('protocol')}://{data.get('host')}:{data.get('port')}")
        add("Status", status)
        add("Exit IP", data.get("exit_ip"))
        add("Country", f"{data.get('country') or ''} ({data.get('country_code') or ''})")
        add("Region / City", f"{data.get('region') or ''} / {data.get('city') or ''}")
        add("ISP", data.get("isp"))
        add("ASN", data.get("asn"))
        add("Organization", data.get("organization"))
        add("Classification", f"{cls} ({(data.get('classification_confidence') or 0)*100:.0f}% confidence)")
        add("Anonymity", str(data.get("anonymity")).title())
        add("DNS status", data.get("dns_status"))
        add("Latency", f"{data.get('latency')} ms" if data.get("latency") is not None else None)
        add("Reliability", f"{data.get('reliability')}%")
        add("Uptime", f"{data.get('uptime')}%")
        add("Score", f"{data.get('score')}")
        add("Source", data.get("source"))
        add("Discovered", data.get("discovered_at"))
        add("Last checked", data.get("last_checked_at"))
        add("Successes / Failures", f"{data.get('success_count')} / {data.get('failure_count')}")
        return w

    def _quality_tab(self, score_components: str | None, evidence: str | None) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(self._heading("Quality score breakdown"))
        if score_components:
            try:
                comps = json.loads(score_components)
                for name, value in comps.items():
                    lbl = QLabel(name.title())
                    lbl.setFixedWidth(140)
                    bar = QLabel()
                    pct = max(0.0, min(100.0, float(value)))
                    bar.setStyleSheet(
                        f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                        f"stop:0 {self.palette_.accent}, stop:{pct/100:.3f} {self.palette_.accent},"
                        f"stop:{min(0.999,pct/100+0.001):.3f} {self.palette_.input_bg}, stop:1 {self.palette_.input_bg});"
                        f"border-radius:6px; padding:4px;"
                    )
                    bar.setText(f"{value:.0f}")
                    bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    container = QWidget()
                    clay = QHBoxLayout(container)
                    clay.setContentsMargins(0, 0, 0, 0)
                    clay.addWidget(lbl)
                    clay.addWidget(bar, 1)
                    layout.addWidget(container)
            except (json.JSONDecodeError, ValueError):
                layout.addWidget(QLabel("No score breakdown available"))
        else:
            layout.addWidget(QLabel("Not scored yet"))

        layout.addWidget(self._heading("Classification evidence"))
        if evidence:
            try:
                items = json.loads(evidence)
                for e in items:
                    layout.addWidget(QLabel(f"• {e}"))
            except (json.JSONDecodeError, ValueError):
                layout.addWidget(QLabel(str(evidence)))
        else:
            layout.addWidget(QLabel("No classification evidence recorded"))
        layout.addStretch(1)
        return w

    def _history_tab(self, latencies: list[float]) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(self._heading("Latency history"))
        chart = LineChart(self.palette_, "Latency (ms) over recent checks")
        chart.set_series(latencies)
        layout.addWidget(chart)
        if not latencies:
            layout.addWidget(QLabel("No history recorded yet."))
        return w

    def _tests_tab(self, tests: list) -> QWidget:
        table = QTableWidget(len(tests), 5)
        table.setHorizontalHeaderLabels(["When", "Profile", "Status", "Latency", "Error"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r, t in enumerate(tests):
            table.setItem(r, 0, QTableWidgetItem(t.tested_at.strftime("%Y-%m-%d %H:%M") if t.tested_at else ""))
            table.setItem(r, 1, QTableWidgetItem(t.profile))
            table.setItem(r, 2, QTableWidgetItem(t.status))
            table.setItem(r, 3, QTableWidgetItem(f"{t.response_time_ms:.0f}" if t.response_time_ms else "—"))
            table.setItem(r, 4, QTableWidgetItem(t.error_detail or ""))
        table.resizeColumnsToContents()
        return table

    def _heading(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{self.palette_.accent}; font-weight:600; margin-top:8px;")
        return lbl
