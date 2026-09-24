"""Dashboard page: KPI cards, charts and recent activity."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.database import repository as repo
from app.ui.pages.base import BasePage
from app.ui.widgets.charts import BarChart, DonutChart
from app.ui.widgets.common import Card, StatCard


class DashboardPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Dashboard", "Overview of your proxy intelligence")

        # KPI cards.
        self._cards: dict[str, StatCard] = {}
        card_grid = QGridLayout()
        card_grid.setSpacing(12)
        specs = [
            ("total", "Total Proxies"), ("working", "Working"),
            ("residential", "Residential"), ("mobile", "Mobile"),
            ("datacenter", "Datacenter"), ("isp", "ISP"),
            ("avg_latency", "Avg Latency (ms)"), ("avg_reliability", "Avg Reliability (%)"),
        ]
        for i, (key, label) in enumerate(specs):
            card = StatCard(label)
            self._cards[key] = card
            card_grid.addWidget(card, i // 4, i % 4)
        self.root.addLayout(card_grid)

        # Charts row.
        charts_row = QHBoxLayout()
        charts_row.setSpacing(12)
        self.class_chart = DonutChart(self.palette_, "Classification")
        self.protocol_chart = DonutChart(self.palette_, "Protocols")
        self.country_chart = BarChart(self.palette_, "Top Countries")
        self.latency_chart = BarChart(self.palette_, "Latency Distribution")
        for chart in (self.class_chart, self.protocol_chart, self.country_chart, self.latency_chart):
            charts_row.addWidget(self._wrap_card(chart))
        self.root.addLayout(charts_row, 1)

        # Recent activity.
        self.activity = self._activity_card()
        self.root.addWidget(self.activity)

    def _wrap_card(self, inner: QWidget) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(inner)
        return card

    def _activity_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        title = QLabel("Recent Activity")
        title.setStyleSheet(f"color:{self.palette_.accent}; font-weight:600;")
        layout.addWidget(title)
        row = QHBoxLayout()
        self._activity_labels: dict[str, QLabel] = {}
        for key, heading in (("discovered", "Latest Discovered"), ("working", "Latest Working"), ("failed", "Latest Failures")):
            col = QVBoxLayout()
            h = QLabel(heading)
            h.setObjectName("StatLabel")
            col.addWidget(h)
            body = QLabel("—")
            body.setWordWrap(True)
            body.setStyleSheet("font-size:12px;")
            body.setAlignment(body.alignment())
            self._activity_labels[key] = body
            col.addWidget(body)
            col.addStretch(1)
            wrap = QWidget()
            wrap.setLayout(col)
            row.addWidget(wrap)
        layout.addLayout(row)
        return card

    # --- refresh ------------------------------------------------------------
    def on_shown(self) -> None:
        self.refresh()

    def on_proxies_changed(self) -> None:
        self.refresh()

    def on_theme_changed(self) -> None:
        for chart in (self.class_chart, self.protocol_chart, self.country_chart, self.latency_chart):
            chart.set_palette(self.palette_)

    def refresh(self) -> None:
        with self.ctx.database.session() as session:
            stats = repo.dashboard_stats(session)
            buckets = repo.latency_buckets(session)
            activity = repo.recent_activity(session, limit=6)
            act_text = {
                "discovered": [f"{p.host}:{p.port} ({p.protocol})" for p in activity["discovered"]],
                "working": [f"{p.host}:{p.port} · {p.country_code or '—'} · {p.latency or '—'}ms" for p in activity["working"]],
                "failed": [f"{p.host}:{p.port} · {p.status}" for p in activity["failed"]],
            }

        self._cards["total"].set_value(stats["total"])
        self._cards["working"].set_value(stats["working"])
        self._cards["residential"].set_value(stats["residential"])
        self._cards["mobile"].set_value(stats["mobile"])
        self._cards["datacenter"].set_value(stats["datacenter"])
        self._cards["isp"].set_value(stats["isp"])
        self._cards["avg_latency"].set_value(f"{stats['avg_latency']:.0f}")
        self._cards["avg_reliability"].set_value(f"{stats['avg_reliability']:.0f}")

        self.class_chart.set_data({k.title(): v for k, v in stats["by_classification"].items() if v})
        self.protocol_chart.set_data({k.upper(): v for k, v in stats["by_protocol"].items() if v})
        self.country_chart.set_data(dict(list(stats["by_country"].items())[:8]))
        self.latency_chart.set_data(buckets)

        for key, lines in act_text.items():
            self._activity_labels[key].setText("\n".join(lines) if lines else "—")
