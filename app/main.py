"""ProxyAtlas GUI entry point."""

from __future__ import annotations

import sys

from app.services.bootstrap import bootstrap


def main() -> int:
    """Launch the ProxyAtlas desktop application."""
    from PyQt6.QtWidgets import QApplication

    from app.services.bootstrap import is_database_empty

    ctx = bootstrap()

    app = QApplication(sys.argv)
    app.setApplicationName("ProxyAtlas")
    app.setOrganizationName("ProxyAtlas Project")

    from app.ui.icons import app_icon
    from app.ui.main_window import MainWindow

    app.setWindowIcon(app_icon())
    window = MainWindow(ctx)
    window.show()

    # Warn if a configured external/custom database location was unavailable.
    if ctx.storage_notice:
        window.toast(ctx.storage_notice, "warning")
    # Onboarding hint if the database is empty.
    elif is_database_empty(ctx):
        window.toast("Welcome to ProxyAtlas! Import a list or run discovery to begin.", "info")

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
