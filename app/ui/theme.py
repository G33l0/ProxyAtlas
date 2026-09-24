"""Centralized theme system: Light, Dark and Midnight.

Each theme is a palette of named colors used both to build a comprehensive QSS
stylesheet (covering windows, sidebar, cards, buttons, inputs, tables, dialogs,
menus, scrollbars) and to color the custom-painted charts and status
indicators. Themes switch live and the choice is persisted in settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QApplication

from app.core.config import Settings


@dataclass(frozen=True)
class Palette:
    name: str
    window: str
    sidebar: str
    sidebar_active: str
    panel: str
    card: str
    border: str
    text: str
    muted: str
    accent: str
    accent2: str
    input_bg: str
    header_bg: str
    alt_row: str
    hover: str
    button: str
    button_text: str
    success: str
    warning: str
    error: str
    info: str
    chart_palette: tuple[str, ...]

    def status_color(self, status: str) -> str:
        return {
            "working": self.success,
            "failed": self.error,
            "timeout": self.warning,
            "auth_required": self.warning,
            "testing": self.info,
            "discovered": self.muted,
            "invalid": self.error,
            "unsupported": self.muted,
            "unknown": self.muted,
        }.get(status, self.muted)


LIGHT = Palette(
    name="light",
    window="#f1f5f9", sidebar="#ffffff", sidebar_active="#e0f2fe",
    panel="#ffffff", card="#ffffff", border="#d8dee9",
    text="#0f172a", muted="#64748b", accent="#0284c7", accent2="#0891b2",
    input_bg="#ffffff", header_bg="#e2e8f0", alt_row="#f8fafc", hover="#e0f2fe",
    button="#0284c7", button_text="#ffffff",
    success="#16a34a", warning="#d97706", error="#dc2626", info="#0284c7",
    chart_palette=("#0284c7", "#0891b2", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0d9488", "#ca8a04"),
)

DARK = Palette(
    name="dark",
    window="#0f172a", sidebar="#111c30", sidebar_active="#1e3a5f",
    panel="#111c30", card="#152238", border="#22314d",
    text="#e2e8f0", muted="#94a3b8", accent="#38bdf8", accent2="#22d3ee",
    input_bg="#0b1526", header_bg="#0e1a2e", alt_row="#0d1728", hover="#1e293b",
    button="#0ea5e9", button_text="#04121f",
    success="#22c55e", warning="#f59e0b", error="#ef4444", info="#38bdf8",
    chart_palette=("#38bdf8", "#22d3ee", "#22c55e", "#f59e0b", "#a78bfa", "#f87171", "#2dd4bf", "#facc15"),
)

MIDNIGHT = Palette(
    name="midnight",
    window="#060a14", sidebar="#0a1020", sidebar_active="#12213f",
    panel="#0a1020", card="#0d1526", border="#1a2540",
    text="#dbeafe", muted="#7c8aa5", accent="#6366f1", accent2="#22d3ee",
    input_bg="#070c18", header_bg="#0a1224", alt_row="#080e1c", hover="#12203c",
    button="#6366f1", button_text="#eef2ff",
    success="#34d399", warning="#fbbf24", error="#fb7185", info="#818cf8",
    chart_palette=("#6366f1", "#22d3ee", "#34d399", "#fbbf24", "#c084fc", "#fb7185", "#2dd4bf", "#f0abfc"),
)

THEMES: dict[str, Palette] = {"light": LIGHT, "dark": DARK, "midnight": MIDNIGHT}


def build_qss(p: Palette) -> str:
    """Return a complete stylesheet for the given palette."""
    return f"""
* {{ outline: none; }}
QWidget {{
    background-color: {p.window};
    color: {p.text};
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background-color: {p.window}; }}

/* Sidebar */
#Sidebar {{ background-color: {p.sidebar}; border-right: 1px solid {p.border}; }}
#Sidebar QPushButton {{
    background: transparent; color: {p.muted}; border: none;
    text-align: left; padding: 11px 16px; border-radius: 8px; font-size: 14px;
}}
#Sidebar QPushButton:hover {{ background-color: {p.hover}; color: {p.text}; }}
#Sidebar QPushButton:checked {{
    background-color: {p.sidebar_active}; color: {p.accent}; font-weight: 600;
}}
#SidebarTitle {{ color: {p.text}; font-size: 18px; font-weight: 700; }}
#SidebarTag {{ color: {p.muted}; font-size: 10px; letter-spacing: 1px; }}

/* Cards / panels */
#Card, .Card {{
    background-color: {p.card}; border: 1px solid {p.border}; border-radius: 12px;
}}
#PageTitle {{ font-size: 22px; font-weight: 700; color: {p.text}; }}
#PageSubtitle {{ color: {p.muted}; font-size: 13px; }}
#StatNumber {{ font-size: 26px; font-weight: 700; color: {p.accent}; }}
#StatLabel {{ color: {p.muted}; font-size: 12px; }}
#EmptyState {{ color: {p.muted}; font-size: 14px; }}

/* Buttons */
QPushButton {{
    background-color: {p.card}; color: {p.text};
    border: 1px solid {p.border}; border-radius: 8px; padding: 7px 14px;
}}
QPushButton:hover {{ background-color: {p.hover}; border-color: {p.accent}; }}
QPushButton:pressed {{ background-color: {p.sidebar_active}; }}
QPushButton:disabled {{ color: {p.muted}; border-color: {p.border}; }}
QPushButton#Primary {{
    background-color: {p.button}; color: {p.button_text};
    border: none; font-weight: 600;
}}
QPushButton#Primary:hover {{ background-color: {p.accent2}; }}
QPushButton#Danger {{ background-color: {p.error}; color: #ffffff; border: none; }}

/* Inputs */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {p.input_bg}; color: {p.text};
    border: 1px solid {p.border}; border-radius: 8px; padding: 6px 10px;
    selection-background-color: {p.accent};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {p.accent};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {p.panel}; color: {p.text};
    border: 1px solid {p.border}; selection-background-color: {p.sidebar_active};
}}

/* Tables */
QTableView, QTreeView, QListView {{
    background-color: {p.panel}; alternate-background-color: {p.alt_row};
    color: {p.text}; border: 1px solid {p.border}; border-radius: 10px;
    gridline-color: {p.border}; selection-background-color: {p.sidebar_active};
    selection-color: {p.text};
}}
QHeaderView::section {{
    background-color: {p.header_bg}; color: {p.accent};
    padding: 7px 8px; border: none; border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border}; font-weight: 600;
}}
QTableView::item {{ padding: 3px 6px; }}
QTableCornerButton::section {{ background-color: {p.header_bg}; border: none; }}

/* Tabs */
QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 10px; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {p.muted}; padding: 8px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {p.accent}; border-bottom: 2px solid {p.accent}; }}

/* Scrollbars */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 6px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {p.accent}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 6px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: {p.accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Menus */
QMenu {{ background-color: {p.panel}; color: {p.text}; border: 1px solid {p.border}; border-radius: 8px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background-color: {p.sidebar_active}; color: {p.accent}; }}
QMenuBar {{ background-color: {p.sidebar}; color: {p.text}; }}
QMenuBar::item:selected {{ background-color: {p.hover}; }}

/* Progress */
QProgressBar {{
    background-color: {p.input_bg}; border: 1px solid {p.border};
    border-radius: 8px; text-align: center; color: {p.text}; height: 16px;
}}
QProgressBar::chunk {{ background-color: {p.accent}; border-radius: 7px; }}

/* Misc */
QToolTip {{
    background-color: {p.panel}; color: {p.text};
    border: 1px solid {p.accent}; border-radius: 6px; padding: 5px;
}}
QGroupBox {{
    border: 1px solid {p.border}; border-radius: 10px; margin-top: 14px; padding-top: 8px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {p.accent}; }}
QStatusBar {{ background-color: {p.sidebar}; color: {p.muted}; border-top: 1px solid {p.border}; }}
QSplitter::handle {{ background-color: {p.border}; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
"""


class ThemeManager:
    """Applies and persists themes."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._current = THEMES.get(settings.get("appearance", "theme", "dark"), DARK)

    @property
    def palette(self) -> Palette:
        return self._current

    def available(self) -> list[str]:
        return list(THEMES.keys())

    def apply(self, app: QApplication, name: str | None = None, persist: bool = True) -> None:
        if name:
            self._current = THEMES.get(name, self._current)
        app.setStyleSheet(build_qss(self._current))
        if persist:
            self.settings.set("appearance", "theme", self._current.name)
            self.settings.save()
