"""Programmatic, theme-aware navigation/action icons.

Icons are drawn with QPainter paths in a requested color, so they stay crisp at
any DPI and recolor instantly on theme change — no external icon files needed.
The application logo/pixmaps are loaded from bundled assets.
"""

from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from app.core.paths import assets_dir


def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pm, painter


def _pen(painter: QPainter, color: str, width: float = 1.8) -> None:
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _draw(name: str, painter: QPainter, color: str, s: int) -> None:
    _pen(painter, color, max(1.6, s / 13))
    m = s * 0.18  # margin
    r = QRectF(m, m, s - 2 * m, s - 2 * m)

    if name == "dashboard":
        half = (s - 2 * m - s * 0.08) / 2
        painter.drawRoundedRect(QRectF(m, m, half, half * 0.9), 3, 3)
        painter.drawRoundedRect(QRectF(m + half + s * 0.08, m, half, half * 1.3), 3, 3)
        painter.drawRoundedRect(QRectF(m, m + half * 1.05, half, half * 1.15), 3, 3)
        painter.drawRoundedRect(QRectF(m + half + s * 0.08, m + half * 1.45, half, half * 0.75), 3, 3)
    elif name == "discovery":
        rr = r.adjusted(0, 0, -s * 0.16, -s * 0.16)
        painter.drawEllipse(rr)
        c = rr.center()
        painter.drawLine(QPointF(c.x() + rr.width() * 0.32, c.y() + rr.height() * 0.32),
                         QPointF(r.right(), r.bottom()))
    elif name == "internet":
        painter.drawEllipse(r)
        painter.drawEllipse(QRectF(r.center().x() - r.width() * 0.18, r.top(), r.width() * 0.36, r.height()))
        painter.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))
        painter.drawLine(QPointF(r.left() + r.width() * 0.08, r.top() + r.height() * 0.28),
                         QPointF(r.right() - r.width() * 0.08, r.top() + r.height() * 0.28))
        painter.drawLine(QPointF(r.left() + r.width() * 0.08, r.bottom() - r.height() * 0.28),
                         QPointF(r.right() - r.width() * 0.08, r.bottom() - r.height() * 0.28))
    elif name == "proxies":
        painter.drawRoundedRect(QRectF(m, m + s * 0.05, s - 2 * m, (s - 2 * m) * 0.26), 3, 3)
        painter.drawRoundedRect(QRectF(m, m + (s - 2 * m) * 0.42, s - 2 * m, (s - 2 * m) * 0.26), 3, 3)
        painter.drawEllipse(QRectF(m + s * 0.06, m + s * 0.11, s * 0.06, s * 0.06))
        painter.drawEllipse(QRectF(m + s * 0.06, m + (s - 2 * m) * 0.42 + s * 0.06, s * 0.06, s * 0.06))
    elif name == "testing":
        painter.drawLine(QPointF(r.left() + r.width() * 0.35, r.top()), QPointF(r.left() + r.width() * 0.35, r.center().y()))
        painter.drawLine(QPointF(r.right() - r.width() * 0.35, r.top()), QPointF(r.right() - r.width() * 0.35, r.center().y()))
        painter.drawLine(QPointF(r.left() + r.width() * 0.35, r.center().y()), QPointF(r.left(), r.bottom()))
        painter.drawLine(QPointF(r.right() - r.width() * 0.35, r.center().y()), QPointF(r.right(), r.bottom()))
        painter.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))
    elif name == "monitoring":
        painter.drawPolyline(QPolygonF([
            QPointF(r.left(), r.center().y()),
            QPointF(r.left() + r.width() * 0.3, r.center().y()),
            QPointF(r.left() + r.width() * 0.45, r.top()),
            QPointF(r.left() + r.width() * 0.6, r.bottom()),
            QPointF(r.left() + r.width() * 0.75, r.center().y()),
            QPointF(r.right(), r.center().y()),
        ]))
    elif name == "collections":
        painter.drawRoundedRect(r, 4, 4)
        painter.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))
        painter.drawLine(QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()))
    elif name == "reports":
        painter.drawRoundedRect(QRectF(m + s * 0.06, m, (s - 2 * m) - s * 0.12, s - 2 * m), 3, 3)
        for i in range(3):
            y = m + s * 0.16 + i * s * 0.16
            painter.drawLine(QPointF(m + s * 0.16, y), QPointF(s - m - s * 0.16, y))
    elif name == "sources":
        painter.drawEllipse(QRectF(r.center().x() - s * 0.07, r.top(), s * 0.14, s * 0.14))
        painter.drawEllipse(QRectF(r.left(), r.bottom() - s * 0.14, s * 0.14, s * 0.14))
        painter.drawEllipse(QRectF(r.right() - s * 0.14, r.bottom() - s * 0.14, s * 0.14, s * 0.14))
        painter.drawLine(r.center(), QPointF(r.left() + s * 0.07, r.bottom() - s * 0.07))
        painter.drawLine(r.center(), QPointF(r.right() - s * 0.07, r.bottom() - s * 0.07))
    elif name == "settings":
        painter.drawEllipse(QRectF(r.center().x() - s * 0.12, r.center().y() - s * 0.12, s * 0.24, s * 0.24))
        painter.drawEllipse(r.adjusted(s * 0.02, s * 0.02, -s * 0.02, -s * 0.02))
    elif name == "about":
        painter.drawEllipse(r)
        painter.drawPoint(QPointF(r.center().x(), r.top() + r.height() * 0.28))
        painter.drawLine(QPointF(r.center().x(), r.center().y() - r.height() * 0.02),
                         QPointF(r.center().x(), r.bottom() - r.height() * 0.2))
    else:
        painter.drawRoundedRect(r, 3, 3)


@lru_cache(maxsize=256)
def glyph_icon(name: str, color: str, size: int = 22) -> QIcon:
    """Return a QIcon for a named glyph in the given color."""
    pm, painter = _canvas(size)
    try:
        _draw(name, painter, color, size)
    finally:
        painter.end()
    return QIcon(pm)


@lru_cache(maxsize=8)
def app_icon() -> QIcon:
    ico = assets_dir() / "logo" / "proxyatlas.ico"
    png = assets_dir() / "logo" / "proxyatlas_icon.png"
    if ico.exists():
        return QIcon(str(ico))
    if png.exists():
        return QIcon(str(png))
    return QIcon()


def logo_pixmap(which: str = "logo") -> QPixmap:
    fname = {
        "logo": "proxyatlas_logo.png",
        "sidebar": "proxyatlas_sidebar.png",
        "icon": "proxyatlas_icon.png",
    }.get(which, "proxyatlas_logo.png")
    path = assets_dir() / "logo" / fname
    if path.exists():
        return QPixmap(str(path))
    return QPixmap()
