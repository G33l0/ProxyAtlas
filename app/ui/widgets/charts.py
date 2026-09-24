"""Lightweight custom-painted charts (bar, donut, line).

No external chart dependency — each chart is a QWidget that paints itself using
the active theme palette, so charts restyle instantly on theme change. Empty
data renders a friendly placeholder rather than an empty canvas.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from app.ui.theme import Palette


class _BaseChart(QWidget):
    def __init__(self, palette: Palette, title: str = "", parent=None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._title = title
        self.setMinimumHeight(180)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def _placeholder(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(self._palette.muted)))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")

    def _draw_title(self, painter: QPainter) -> int:
        if not self._title:
            return 6
        painter.setPen(QPen(QColor(self._palette.text)))
        font = QFont(self.font())
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(10, 20, self._title)
        return 34


class BarChart(_BaseChart):
    def __init__(self, palette: Palette, title: str = "", parent=None) -> None:
        super().__init__(palette, title, parent)
        self._data: list[tuple[str, float]] = []

    def set_data(self, data: dict[str, float] | list[tuple[str, float]]) -> None:
        self._data = list(data.items()) if isinstance(data, dict) else list(data)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        top = self._draw_title(painter)
        if not self._data:
            self._placeholder(painter)
            painter.end()
            return
        w = self.width()
        h = self.height() - top - 26
        left = 12
        n = len(self._data)
        gap = 10
        bar_w = max(6, (w - 2 * left - gap * (n - 1)) / n)
        max_v = max((v for _, v in self._data), default=1) or 1
        colors = self._palette.chart_palette
        for i, (label, value) in enumerate(self._data):
            x = left + i * (bar_w + gap)
            bh = (value / max_v) * (h - 10)
            y = top + h - bh
            painter.setBrush(QColor(colors[i % len(colors)]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y, bar_w, bh), 4, 4)
            painter.setPen(QPen(QColor(self._palette.muted)))
            painter.drawText(QRectF(x - 6, top + h + 2, bar_w + 12, 20),
                             Qt.AlignmentFlag.AlignCenter, str(label)[:10])
            painter.setPen(QPen(QColor(self._palette.text)))
            painter.drawText(QRectF(x - 6, y - 18, bar_w + 12, 16),
                             Qt.AlignmentFlag.AlignCenter, f"{value:g}")
        painter.end()


class DonutChart(_BaseChart):
    def __init__(self, palette: Palette, title: str = "", parent=None) -> None:
        super().__init__(palette, title, parent)
        self._data: list[tuple[str, float]] = []

    def set_data(self, data: dict[str, float] | list[tuple[str, float]]) -> None:
        items = list(data.items()) if isinstance(data, dict) else list(data)
        self._data = [(k, v) for k, v in items if v]
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        top = self._draw_title(painter)
        if not self._data:
            self._placeholder(painter)
            painter.end()
            return
        total = sum(v for _, v in self._data) or 1
        size = min(self.width() * 0.5, self.height() - top - 16)
        rect = QRectF(16, top, size, size)
        start = 90 * 16
        colors = self._palette.chart_palette
        for i, (_, value) in enumerate(self._data):
            span = -int(value / total * 360 * 16)
            painter.setBrush(QColor(colors[i % len(colors)]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(rect, start, span)
            start += span
        # Donut hole.
        hole = rect.adjusted(size * 0.28, size * 0.28, -size * 0.28, -size * 0.28)
        painter.setBrush(QColor(self._palette.card))
        painter.drawEllipse(hole)
        # Legend.
        lx = rect.right() + 20
        ly = top + 4
        painter.setFont(self.font())
        for i, (label, value) in enumerate(self._data[:8]):
            painter.setBrush(QColor(colors[i % len(colors)]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(lx, ly + i * 22, 12, 12), 3, 3)
            painter.setPen(QPen(QColor(self._palette.text)))
            pct = value / total * 100
            painter.drawText(int(lx + 20), int(ly + i * 22 + 11), f"{str(label)[:14]}  {pct:.0f}%")
        painter.end()


class LineChart(_BaseChart):
    def __init__(self, palette: Palette, title: str = "", parent=None) -> None:
        super().__init__(palette, title, parent)
        self._series: list[float] = []

    def set_series(self, values: list[float]) -> None:
        self._series = list(values)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        top = self._draw_title(painter)
        if len(self._series) < 2:
            self._placeholder(painter)
            painter.end()
            return
        w = self.width() - 24
        h = self.height() - top - 20
        max_v = max(self._series) or 1
        min_v = min(self._series)
        span = (max_v - min_v) or 1
        step = w / (len(self._series) - 1)
        points = QPolygonF()
        for i, v in enumerate(self._series):
            x = 12 + i * step
            y = top + h - ((v - min_v) / span) * (h - 10)
            points.append(QPointF(x, y))
        pen = QPen(QColor(self._palette.accent))
        pen.setWidthF(2.2)
        painter.setPen(pen)
        painter.drawPolyline(points)
        painter.setBrush(QColor(self._palette.accent2))
        painter.setPen(Qt.PenStyle.NoPen)
        for pt in points:
            painter.drawEllipse(pt, 2.6, 2.6)
        painter.end()
