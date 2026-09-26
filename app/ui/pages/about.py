"""About page: branding, version and architecture overview."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app import __tagline__, __version__
from app.ui.icons import logo_pixmap
from app.ui.pages.base import BasePage
from app.ui.widgets.common import Card


class AboutPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "About", "")
        # Replace default header with logo.
        card = Card()
        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.setSpacing(10)

        logo = QLabel()
        pm = logo_pixmap("logo")
        if not pm.isNull():
            logo.setPixmap(pm.scaledToWidth(420, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        version = QLabel(f"Version {__version__}")
        version.setObjectName("PageSubtitle")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        tagline = QLabel(__tagline__)
        tagline.setStyleSheet(f"color:{self.palette_.accent}; font-size:15px; font-weight:600;")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)

        desc = QLabel(
            "ProxyAtlas is a professional network utility for discovering, validating, "
            "classifying, monitoring and managing proxy endpoints.\n\n"
            "The discovery engine, validation engine, intelligence system, classification "
            "engine, monitoring system and UI are architected to evolve independently, so "
            "additional proxy sources, protocols, intelligence providers and discovery "
            "mechanisms can be added in future releases."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setMaximumWidth(620)
        layout.addWidget(desc, alignment=Qt.AlignmentFlag.AlignCenter)

        features = QLabel(
            "Protocols: HTTP / HTTPS / SOCKS4 / SOCKS5\n"
            "Classifications: Residential / Mobile / Datacenter / ISP / Business / "
            "Educational / Government / Unknown\n"
            "Storage: SQLite + SQLAlchemy + Alembic"
        )
        features.setObjectName("PageSubtitle")
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)
        features.setWordWrap(True)
        layout.addWidget(features)

        self.root.addWidget(card)
        self.root.addStretch(1)

        footer = QLabel("© 2026 ProxyAtlas Project / MIT License")
        footer.setObjectName("StatLabel")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.root.addWidget(footer)

    def _placeholder(self) -> QWidget:
        return QWidget()
