"""Base page with shared helpers."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from app.services.app_context import AppContext
from app.ui.theme import Palette
from app.ui.widgets.common import SectionTitle


class BasePage(QWidget):
    """Common base for all pages."""

    def __init__(self, ctx: AppContext, main_window, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.ctx = ctx
        self.main = main_window
        self._title = title
        self._subtitle = subtitle
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 20, 24, 20)
        self.root.setSpacing(14)
        self.header = SectionTitle(title, subtitle)
        self.root.addWidget(self.header)

    @property
    def palette_(self) -> Palette:
        return self.main.theme_manager.palette

    def toast(self, message: str, level: str = "info") -> None:
        self.main.toast(message, level)

    def on_shown(self) -> None:
        """Called when the page becomes visible. Override to refresh."""

    def on_theme_changed(self) -> None:
        """Called when the theme changes. Override to restyle custom widgets."""

    def on_proxies_changed(self) -> None:
        """Called when the proxy dataset changes. Override to refresh."""
