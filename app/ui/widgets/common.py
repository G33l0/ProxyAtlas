"""Common reusable widgets: stat cards, empty states, toasts, badges."""

from __future__ import annotations

from PyQt6.QtCore import QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Palette


class Card(QFrame):
    """A rounded panel container."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")


class StatCard(Card):
    """A dashboard metric card with a big number and a label."""

    def __init__(self, label: str, value: str = "0", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(2)
        self._value = QLabel(value)
        self._value.setObjectName("StatNumber")
        self._label = QLabel(label)
        self._label.setObjectName("StatLabel")
        layout.addWidget(self._value)
        layout.addWidget(self._label)

    def set_value(self, value: str) -> None:
        self._value.setText(str(value))

    def set_accent(self, color: str) -> None:
        self._value.setStyleSheet(f"color: {color};")


class SectionTitle(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        layout.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("PageSubtitle")
            layout.addWidget(s)
        self._subtitle = subtitle


class EmptyState(QWidget):
    """A centered empty-state message."""

    def __init__(self, message: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel(message)
        self._label.setObjectName("EmptyState")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

    def set_message(self, message: str) -> None:
        self._label.setText(message)


class Toast(QLabel):
    """A transient notification shown at the bottom of its parent."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.hide()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, palette: Palette, level: str = "info", msec: int = 3000) -> None:
        color = {
            "info": palette.info,
            "success": palette.success,
            "warning": palette.warning,
            "error": palette.error,
        }.get(level, palette.info)
        self.setStyleSheet(
            f"background-color: {palette.panel}; color: {palette.text};"
            f"border: 1px solid {color}; border-left: 4px solid {color};"
            f"border-radius: 8px; padding: 10px 16px; font-size: 13px;"
        )
        self.setText(text)
        self.adjustSize()
        self._reposition()
        self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(msec)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        self.setFixedWidth(min(420, parent.width() - 60))
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 28
        self.move(max(10, x), max(10, y))

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(400)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.hide)
        self._anim.start()


class Badge(QLabel):
    """A small colored status pill."""

    def __init__(self, text: str = "", color: str = "#888", parent=None) -> None:
        super().__init__(text, parent)
        self.set_color(color)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(
            f"background-color: {color}22; color: {color};"
            f"border: 1px solid {color}; border-radius: 8px; padding: 2px 8px; font-size: 11px;"
        )


def hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    return line


class Row(QWidget):
    """Horizontal container helper."""

    def __init__(self, *widgets: QWidget, spacing: int = 8, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for w in widgets:
            layout.addWidget(w)
        self.layout_ = layout
