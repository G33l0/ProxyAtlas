"""ProxyAtlas main window: sidebar navigation + stacked pages."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import __tagline__, __version__
from app.core.events import Topics, bus
from app.database.filters import FilterSpec
from app.services.app_context import AppContext
from app.ui.icons import app_icon, glyph_icon, logo_pixmap
from app.ui.pages.about import AboutPage
from app.ui.pages.collections import CollectionsPage
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.discovery import DiscoveryPage
from app.ui.pages.internet_discovery import InternetDiscoveryPage
from app.ui.pages.monitoring import MonitoringPage
from app.ui.pages.proxies import ProxiesPage
from app.ui.pages.reports import ReportsPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.sources import SourcesPage
from app.ui.pages.testing import TestingPage
from app.ui.theme import ThemeManager
from app.ui.widgets.common import Toast

NAV = [
    ("dashboard", "Dashboard", "dashboard"),
    ("discovery", "Discovery", "discovery"),
    ("internet", "Internet Discovery", "internet"),
    ("proxies", "Proxies", "proxies"),
    ("testing", "Testing", "testing"),
    ("monitoring", "Monitoring", "monitoring"),
    ("collections", "Collections", "collections"),
    ("reports", "Reports", "reports"),
    ("sources", "Sources", "sources"),
    ("settings", "Settings", "settings"),
    ("about", "About", "about"),
]


class MainWindow(QMainWindow):
    proxies_changed = pyqtSignal()
    theme_changed = pyqtSignal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.theme_manager = ThemeManager(ctx.settings)
        self.setWindowTitle(f"ProxyAtlas - {__tagline__}")
        self.setWindowIcon(app_icon())
        self.resize(1360, 860)
        self.setMinimumSize(1040, 680)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Instantiate pages.
        self.pages: dict[str, QWidget] = {}
        self._page_order: list[str] = []
        page_classes = {
            "dashboard": DashboardPage, "discovery": DiscoveryPage,
            "internet": InternetDiscoveryPage, "proxies": ProxiesPage,
            "testing": TestingPage, "monitoring": MonitoringPage,
            "collections": CollectionsPage, "reports": ReportsPage,
            "sources": SourcesPage, "settings": SettingsPage, "about": AboutPage,
        }
        for key, _label, _icon in NAV:
            page = page_classes[key](ctx, self)
            self.pages[key] = page
            self.stack.addWidget(page)
            self._page_order.append(key)

        # Toast overlay.
        self.toast_widget = Toast(self)

        # Status bar.
        self._status = QLabel("Ready")
        self.statusBar().addWidget(self._status)
        self._job_status = QLabel("")
        self.statusBar().addPermanentWidget(self._job_status)

        # Signals.
        self.proxies_changed.connect(self._broadcast_proxies_changed)
        bus.subscribe(Topics.JOB_UPDATED, self._on_job_event)
        bus.subscribe(Topics.JOB_FINISHED, self._on_job_event)

        self._setup_shortcuts()
        self.apply_theme(self.theme_manager.palette.name, persist=False)
        self.navigate("dashboard")

        # Background monitoring scheduler: fires due monitoring jobs automatically.
        self._active_monitor_jobs: set[int] = set()
        self._monitor_workers: list = []
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(60_000)  # check once a minute
        self._monitor_timer.timeout.connect(self._tick_monitors)
        self._monitor_timer.start()

    # --- sidebar ------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        logo = QLabel()
        pm = logo_pixmap("sidebar")
        if not pm.isNull():
            logo.setPixmap(pm.scaledToWidth(190, Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText("ProxyAtlas")
            logo.setObjectName("SidebarTitle")
        layout.addWidget(logo)
        tag = QLabel("DISCOVER / VALIDATE / ANALYZE")
        tag.setObjectName("SidebarTag")
        layout.addWidget(tag)
        layout.addSpacing(14)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, label, icon in NAV:
            btn = QPushButton(f"  {label}")
            btn.setCheckable(True)
            btn.setIcon(glyph_icon(icon, self._icon_color(), 20))
            btn.clicked.connect(lambda _c, k=key: self.navigate(k))
            layout.addWidget(btn)
            self._nav_group.addButton(btn)
            self._nav_buttons[key] = btn

        layout.addStretch(1)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("SidebarTag")
        layout.addWidget(ver)
        return sidebar

    def _icon_color(self) -> str:
        return self.theme_manager.palette.muted

    # --- navigation ---------------------------------------------------------
    def navigate(self, key: str) -> None:
        if key not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[key])
        if key in self._nav_buttons:
            self._nav_buttons[key].setChecked(True)
        page = self.pages[key]
        if hasattr(page, "on_shown"):
            page.on_shown()
        self._status.setText(dict((k, lbl) for k, lbl, _ in NAV).get(key, "Ready"))

    def open_proxies_with_filter(self, spec: FilterSpec) -> None:
        proxies = self.pages["proxies"]
        self.navigate("proxies")
        proxies.filter_bar.load_spec(spec)

    # --- theme --------------------------------------------------------------
    def apply_theme(self, name: str, persist: bool = True) -> None:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        self.theme_manager.apply(app, name, persist=persist)
        # Refresh nav icons + custom-painted pages.
        for key, btn in self._nav_buttons.items():
            icon_name = dict((k, ic) for k, _l, ic in NAV)[key]
            btn.setIcon(glyph_icon(icon_name, self._icon_color(), 20))
        for page in self.pages.values():
            if hasattr(page, "on_theme_changed"):
                page.on_theme_changed()
        self.theme_changed.emit()

    # --- cross-page notifications ------------------------------------------
    def notify_proxies_changed(self) -> None:
        self.proxies_changed.emit()

    def _broadcast_proxies_changed(self) -> None:
        for page in self.pages.values():
            if hasattr(page, "on_proxies_changed"):
                page.on_proxies_changed()

    # --- jobs / status ------------------------------------------------------
    def _on_job_event(self, snapshot: dict) -> None:
        state = snapshot.get("state")
        label = snapshot.get("label", "Job")
        if state == "running":
            self._job_status.setText(f"> {label}: {snapshot.get('progress', 0):.0f}%")
        elif state in ("completed", "failed", "cancelled"):
            self._job_status.setText(f"{label}: {state}")

    # --- background monitoring scheduler -----------------------------------
    def _tick_monitors(self) -> None:
        """Run any enabled monitoring jobs that are due, without overlap."""
        from datetime import datetime, timezone

        from app.database import repository as repo
        from app.workers.monitoring_worker import MonitoringWorker

        now = datetime.now(timezone.utc)
        try:
            with self.ctx.database.session() as session:
                jobs = repo.list_monitoring_jobs(session)
                due = []
                for j in jobs:
                    if not j.enabled or j.id in self._active_monitor_jobs:
                        continue
                    next_run = j.next_run_at
                    if next_run is not None and next_run.tzinfo is None:
                        next_run = next_run.replace(tzinfo=timezone.utc)
                    if next_run is None or next_run <= now:
                        due.append((j.id, j.target_type, j.target_ref or ""))
        except Exception:  # noqa: BLE001
            return

        for job_id, target_type, target_ref in due:
            self._active_monitor_jobs.add(job_id)
            worker = MonitoringWorker(self.ctx, job_id, target_type, target_ref)
            worker.completed.connect(lambda out, jid=job_id, w=worker: self._monitor_done(jid, w))
            worker.failed.connect(lambda err, jid=job_id, w=worker: self._monitor_done(jid, w))
            self._monitor_workers.append(worker)
            worker.start()

    def _monitor_done(self, job_id: int, worker) -> None:
        self._active_monitor_jobs.discard(job_id)
        if worker in self._monitor_workers:
            self._monitor_workers.remove(worker)
        page = self.pages.get("monitoring")
        if page is not None and self.stack.currentWidget() is page:
            page.refresh()

    # --- toast --------------------------------------------------------------
    def toast(self, message: str, level: str = "info") -> None:
        self.toast_widget.show_message(message, self.theme_manager.palette, level)
        self._status.setText(message)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.toast_widget.isVisible():
            self.toast_widget._reposition()

    # --- shortcuts ----------------------------------------------------------
    def _setup_shortcuts(self) -> None:
        def sc(seq: str, slot):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(slot)
            return s

        sc("Ctrl+I", lambda: (self.navigate("discovery"), self.pages["discovery"]._import_file()))
        sc("Ctrl+R", self._refresh_current)
        sc("F5", self._refresh_current)
        sc("Ctrl+F", self._focus_search)
        sc("Ctrl+E", self._export_shortcut)
        sc("Ctrl+Shift+T", lambda: self.navigate("testing"))

    def _refresh_current(self) -> None:
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()
        elif hasattr(page, "on_shown"):
            page.on_shown()

    def _focus_search(self) -> None:
        self.navigate("proxies")
        self.pages["proxies"].focus_search()

    def _export_shortcut(self) -> None:
        self.navigate("proxies")
        self.pages["proxies"]._export()

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.ctx.settings.save()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
