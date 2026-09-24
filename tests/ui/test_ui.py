"""UI tests: startup, navigation, theme switching, import, filtering, settings.

These use pytest-qt's ``qtbot`` and run under the offscreen Qt platform.
"""

from __future__ import annotations

import pytest

from app.core.enums import Protocol, ValidationStatus
from app.core.models import (
    Endpoint,
    ProxyCandidate,
    ValidationResult,
)
from app.database import repository as repo
from app.database.filters import FilterSpec

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture()
def window(ctx, qtbot):
    from app.ui.main_window import MainWindow

    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win.show()
    return win


def _seed(ctx, n=5, working=True):
    with ctx.database.session() as s:
        for i in range(n):
            ep = Endpoint(f"10.0.0.{i}", 8080, Protocol.HTTP)
            p = repo.upsert_proxy_from_candidate(s, ProxyCandidate(ep, source="seed"), ctx.cipher)
            status = ValidationStatus.WORKING if working else ValidationStatus.FAILED
            repo.apply_validation_result(s, p, ValidationResult(ep, status, latency_ms=100 + i, exit_ip=f"5.5.5.{i}", samples=1, successes=1 if working else 0))


def test_startup_shows_dashboard(window):
    assert window.stack.currentWidget() is window.pages["dashboard"]


def test_navigation_all_pages(window):
    from app.ui.main_window import NAV

    for key, _label, _icon in NAV:
        window.navigate(key)
        assert window.stack.currentWidget() is window.pages[key]


def test_theme_switching(window):
    for theme in ("light", "dark", "midnight"):
        window.apply_theme(theme, persist=False)
        assert window.theme_manager.palette.name == theme


def test_proxies_populate_and_filter(window, ctx):
    _seed(ctx, 5, working=True)
    _seed(ctx, 0)  # noop
    with ctx.database.session() as s:
        # add a failed one
        ep = Endpoint("10.0.1.1", 80, Protocol.HTTP)
        p = repo.upsert_proxy_from_candidate(s, ProxyCandidate(ep, source="seed"), ctx.cipher)
        repo.apply_validation_result(s, p, ValidationResult(ep, ValidationStatus.FAILED))
    page = window.pages["proxies"]
    window.navigate("proxies")
    assert page.model.rowCount() == 6
    # Apply working-only filter.
    page._on_filter_applied(FilterSpec().add("status", "eq", "working"))
    assert page.model.rowCount() == 5


def test_import_via_discovery_page(window, ctx, tmp_path):
    f = tmp_path / "imp.txt"
    f.write_text("1.2.3.4:8080\n5.6.7.8:3128\n")
    # Directly exercise the import path used by the page.
    from app.discovery.importer import ProxyImporter

    cands, _ = ProxyImporter().import_file(str(f))
    with ctx.database.session() as s:
        for c in cands:
            repo.add_discovery_candidate(s, c, ctx.cipher)
    page = window.pages["discovery"]
    window.navigate("discovery")
    page.refresh()
    assert page.queue_table.rowCount() == 2


def test_settings_save_and_theme_apply(window, ctx):
    page = window.pages["settings"]
    window.navigate("settings")
    page._widgets["appearance.theme"].setCurrentText("midnight")
    page._widgets["testing.concurrency"].setValue(77)
    page._save()
    assert ctx.settings.get("testing", "concurrency") == 77
    assert window.theme_manager.palette.name == "midnight"


def test_export_selected_rows(window, ctx, tmp_path):
    _seed(ctx, 3, working=True)
    page = window.pages["proxies"]
    window.navigate("proxies")
    page.table.selectAll()
    out = tmp_path / "sel.txt"
    page._export_selected_rows({"fmt": "txt", "path": str(out), "working_only": True, "txt_format": "ip_port"})
    assert out.exists()
    assert len(out.read_text().strip().splitlines()) == 3


def test_collections_open_applies_filter(window, ctx):
    _seed(ctx, 4, working=True)
    with ctx.database.session() as s:
        repo.save_collection(s, "All working", FilterSpec().add("status", "eq", "working"))
    page = window.pages["collections"]
    window.navigate("collections")
    page.refresh()
    assert page.table.rowCount() == 1
