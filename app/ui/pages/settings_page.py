"""Settings page with grouped tabs bound to the settings store."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QWidget,
)

from app.ui.pages.base import BasePage


class SettingsPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Settings", "Configure ProxyAtlas behaviour")
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)
        self._widgets: dict[str, QWidget] = {}

        self._build_general()
        self._build_appearance()
        self._build_discovery()
        self._build_testing()
        self._build_monitoring()
        self._build_intelligence()
        self._build_providers()
        self._build_database()
        self._build_reports()
        self._build_logging()

        actions = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save)
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset)
        actions.addStretch(1)
        actions.addWidget(reset_btn)
        actions.addWidget(save_btn)
        self.root.addLayout(actions)

    # --- helpers ------------------------------------------------------------
    def _tab(self, title: str) -> QFormLayout:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)
        self.tabs.addTab(w, title)
        return form

    def _line(self, key, value):
        e = QLineEdit(str(value if value is not None else ""))
        self._widgets[key] = e
        return e

    def _spin(self, key, value, lo=0, hi=100000):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(int(value or 0))
        self._widgets[key] = s
        return s

    def _dspin(self, key, value, lo=0.0, hi=100000.0, step=0.5):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(float(value or 0))
        self._widgets[key] = s
        return s

    def _combo(self, key, items, value):
        c = QComboBox()
        c.addItems(items)
        idx = c.findText(str(value))
        if idx >= 0:
            c.setCurrentIndex(idx)
        self._widgets[key] = c
        return c

    def _textarea(self, key, value):
        t = QPlainTextEdit()
        if isinstance(value, list):
            value = "\n".join(str(v) for v in value)
        t.setPlainText(str(value or ""))
        t.setFixedHeight(90)
        self._widgets[key] = t
        return t

    def _get(self, section, key, default=None):
        return self.ctx.settings.get(section, key, default)

    # --- tabs ---------------------------------------------------------------
    def _build_general(self):
        f = self._tab("General")
        f.addRow("Results page size", self._spin("general.results_page_size", self._get("general", "results_page_size", 200), 20, 5000))
        f.addRow("Confirm destructive actions", self._combo("general.confirm_destructive", ["true", "false"], str(self._get("general", "confirm_destructive", True)).lower()))
        f.addRow("Auto-recover jobs", self._combo("general.auto_recover_jobs", ["true", "false"], str(self._get("general", "auto_recover_jobs", True)).lower()))

    def _build_appearance(self):
        f = self._tab("Appearance")
        f.addRow("Theme", self._combo("appearance.theme", ["light", "dark", "midnight"], self._get("appearance", "theme", "dark")))

    def _build_discovery(self):
        f = self._tab("Discovery")
        f.addRow("Auto-deduplicate", self._combo("discovery.auto_dedupe", ["true", "false"], str(self._get("discovery", "auto_dedupe", True)).lower()))
        f.addRow("Auto-validate after discovery", self._combo("discovery.auto_validate_after_discovery", ["true", "false"], str(self._get("discovery", "auto_validate_after_discovery", False)).lower()))
        f.addRow("Feed timeout (s)", self._dspin("discovery.default_feed_timeout", self._get("discovery", "default_feed_timeout", 20.0), 1, 300))

    def _build_testing(self):
        f = self._tab("Testing")
        f.addRow("Timeout (s)", self._dspin("testing.timeout", self._get("testing", "timeout", 12.0), 1, 120))
        f.addRow("Concurrency", self._spin("testing.concurrency", self._get("testing", "concurrency", 40), 1, 500))
        f.addRow("Retries", self._spin("testing.retries", self._get("testing", "retries", 1), 0, 10))
        f.addRow("Default profile", self._combo("testing.default_profile", ["quick", "standard", "deep"], self._get("testing", "default_profile", "standard")))
        f.addRow("Validation endpoints", self._textarea("testing.validation_endpoints", self._get("testing", "validation_endpoints", [])))
        f.addRow("Judge endpoint", self._line("testing.judge_endpoint", self._get("testing", "judge_endpoint", "")))

    def _build_monitoring(self):
        f = self._tab("Monitoring")
        f.addRow("Default interval (min)", self._spin("monitoring.default_interval_minutes", self._get("monitoring", "default_interval_minutes", 30), 1, 10080))
        f.addRow("History retention (days)", self._spin("monitoring.history_retention_days", self._get("monitoring", "history_retention_days", 90), 1, 3650))

    def _build_intelligence(self):
        f = self._tab("Intelligence")
        f.addRow("Enabled", self._combo("intelligence.enabled", ["true", "false"], str(self._get("intelligence", "enabled", True)).lower()))
        f.addRow("Reverse DNS", self._combo("intelligence.reverse_dns", ["true", "false"], str(self._get("intelligence", "reverse_dns", True)).lower()))

    def _build_providers(self):
        f = self._tab("Providers")
        providers = self._get("intelligence", "providers", {}) or {}
        ipinfo = providers.get("ipinfo", {})
        f.addRow("ipinfo.io token", self._line("providers.ipinfo.token", ipinfo.get("token", "")))
        f.addRow("Enable ipinfo.io", self._combo("providers.ipinfo.enabled", ["true", "false"], str(ipinfo.get("enabled", False)).lower()))
        ipapi = providers.get("ip-api", {})
        f.addRow("Enable ip-api.com", self._combo("providers.ip-api.enabled", ["true", "false"], str(ipapi.get("enabled", True)).lower()))

    def _build_database(self):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

        f = self._tab("Database")

        # Current effective location (read-only info).
        current = QLabel(getattr(self.ctx, "database_path", "") or "default location")
        current.setObjectName("StatLabel")
        current.setWordWrap(True)
        f.addRow("Current database", current)

        # Custom path with folder/file browse (supports external drives).
        path_edit = self._line("database.path", self._get("database", "path", ""))
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(path_edit)
        browse_dir = QPushButton("Folder…")
        browse_dir.clicked.connect(lambda: self._browse_db_folder(path_edit))
        browse_file = QPushButton("File…")
        browse_file.clicked.connect(lambda: self._browse_db_file(path_edit))
        rl.addWidget(browse_dir)
        rl.addWidget(browse_file)
        f.addRow("Database path (blank = default)", row)

        hint = QLabel(
            "Point this at an external drive or any folder to keep the database "
            "off the system disk. If the drive is unavailable at launch, "
            "ProxyAtlas falls back to the default location."
        )
        hint.setObjectName("StatLabel")
        hint.setWordWrap(True)
        f.addRow("", hint)

        relocate = QPushButton("Relocate database to this path now")
        relocate.clicked.connect(lambda: self._relocate_database(path_edit))
        f.addRow("", relocate)

        f.addRow("Batch size", self._spin("database.batch_size", self._get("database", "batch_size", 500), 50, 10000))

    def _browse_db_folder(self, edit) -> None:
        from PyQt6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "Select database folder (e.g. external drive)")
        if folder:
            edit.setText(folder)

    def _browse_db_file(self, edit) -> None:
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "Select database file", "proxyatlas.sqlite", "SQLite (*.sqlite *.db);;All files (*)"
        )
        if path:
            edit.setText(path)

    def _relocate_database(self, edit) -> None:
        from pathlib import Path

        from app.services.storage import relocate_database, validate_db_location

        dest = edit.text().strip()
        if not dest:
            self.toast("Enter or browse to a destination path first", "warning")
            return
        ok, msg = validate_db_location(dest)
        if not ok:
            self.toast(msg, "error")
            return
        current = Path(getattr(self.ctx, "database_path", "") or self.ctx.paths.database_path)
        ok, msg = relocate_database(current, dest, self.ctx.settings)
        self.toast(msg, "success" if ok else "error")

    def _build_reports(self):
        f = self._tab("Reports")
        f.addRow("Output directory (blank = default)", self._line("reports.output_dir", self._get("reports", "output_dir", "")))

    def _build_logging(self):
        f = self._tab("Logging")
        f.addRow("Log level", self._combo("logging.level", ["DEBUG", "INFO", "WARNING", "ERROR"], self._get("logging", "level", "INFO")))
        f.addRow("Max log size (bytes)", self._spin("logging.max_bytes", self._get("logging", "max_bytes", 2000000), 100000, 100000000))
        f.addRow("Backup count", self._spin("logging.backup_count", self._get("logging", "backup_count", 5), 1, 50))

    # --- save ---------------------------------------------------------------
    def _coerce(self, widget):
        if isinstance(widget, QComboBox):
            text = widget.currentText()
            if text in ("true", "false"):
                return text == "true"
            return text
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QPlainTextEdit):
            return [ln.strip() for ln in widget.toPlainText().splitlines() if ln.strip()]
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        return None

    def _save(self) -> None:
        providers = self.ctx.settings.get("intelligence", "providers", {}) or {}
        for key, widget in self._widgets.items():
            value = self._coerce(widget)
            parts = key.split(".")
            if parts[0] == "providers":
                # providers.<name>.<field>
                _, pname, field = parts
                providers.setdefault(pname, {})[field] = value
            else:
                section, field = parts[0], parts[1]
                # textarea for validation_endpoints already list
                self.ctx.settings.set(section, field, value)
        self.ctx.settings.set("intelligence", "providers", providers)
        self.ctx.settings.save()
        # Apply theme + reconfigure intelligence live.
        self.main.apply_theme(self.ctx.settings.get("appearance", "theme", "dark"))
        self.ctx.intelligence = type(self.ctx.intelligence)()
        self.ctx.intelligence.register_defaults(providers)
        self.toast("Settings saved", "success")

    def _reset(self) -> None:
        from PyQt6.QtWidgets import QMessageBox

        if QMessageBox.question(self, "Reset", "Reset all settings to defaults?") != QMessageBox.StandardButton.Yes:
            return
        self.ctx.settings.reset_to_defaults()
        self.ctx.settings.save()
        self.toast("Settings reset. Restart recommended.", "info")
        self.main.apply_theme(self.ctx.settings.get("appearance", "theme", "dark"))
