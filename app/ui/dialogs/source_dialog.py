"""Add/edit a discovery source with a schema-driven configuration form."""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.enums import Protocol, SourceType
from app.discovery.manager import PROVIDER_REGISTRY

PROVIDER_LABELS = {
    "file": "File (TXT/CSV/JSON)",
    "feed": "Feed URL",
    "api": "API",
    "custom": "Custom list",
    "internet": "Internet discovery",
}


class SourceDialog(QDialog):
    def __init__(self, parent=None, existing: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Discovery Source")
        self.setMinimumWidth(520)
        self._fields: dict[str, QWidget] = {}
        self._existing = existing or {}

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        root.addLayout(form)

        self.name_edit = QLineEdit(self._existing.get("name", ""))
        form.addRow("Name", self.name_edit)

        self.provider_combo = QComboBox()
        for key in PROVIDER_REGISTRY:
            self.provider_combo.addItem(PROVIDER_LABELS.get(key, key), key)
        if self._existing.get("provider"):
            idx = self.provider_combo.findData(self._existing["provider"])
            if idx >= 0:
                self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.currentIndexChanged.connect(self._rebuild_fields)
        form.addRow("Provider", self.provider_combo)

        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(self._existing.get("enabled", True))
        form.addRow("", self.enabled_check)

        self._form = form
        self._dynamic_rows: list[QWidget] = []
        self._rebuild_fields()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _current_provider(self) -> str:
        return self.provider_combo.currentData()

    def _rebuild_fields(self) -> None:
        # Remove old dynamic rows.
        for widget in self._dynamic_rows:
            self._form.removeRow(widget)
        self._dynamic_rows.clear()
        self._fields.clear()

        provider_key = self._current_provider()
        provider_cls = PROVIDER_REGISTRY.get(provider_key)
        if provider_cls is None:
            return
        schema = provider_cls({}).config_schema()
        existing_cfg = self._existing.get("config", {}) if self._existing.get("provider") == provider_key else {}

        for field_name, meta in schema.items():
            widget = self._make_field(meta, existing_cfg.get(field_name))
            self._fields[field_name] = widget
            label = meta.get("label", field_name)
            container = self._wrap_field(meta, widget)
            self._form.addRow(label, container)
            self._dynamic_rows.append(container)

    def _make_field(self, meta: dict, value: Any) -> QWidget:
        ftype = meta.get("type", "text")
        if ftype == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
            return w
        if ftype == "number":
            w = QSpinBox()
            w.setRange(0, 1_000_000)
            w.setValue(int(value) if value not in (None, "") else 0)
            return w
        if ftype == "textarea":
            w = QPlainTextEdit()
            if isinstance(value, list):
                value = "\n".join(str(v) for v in value)
            w.setPlainText(str(value or ""))
            w.setFixedHeight(90)
            return w
        if ftype == "protocol":
            w = QComboBox()
            w.addItems([p.value for p in Protocol])
            if value:
                i = w.findText(str(value))
                if i >= 0:
                    w.setCurrentIndex(i)
            return w
        if ftype == "choice":
            w = QComboBox()
            w.addItems([str(c) for c in meta.get("choices", [])])
            if value:
                i = w.findText(str(value))
                if i >= 0:
                    w.setCurrentIndex(i)
            return w
        # text / url / path / secret
        w = QLineEdit(str(value or ""))
        if ftype == "secret":
            w.setEchoMode(QLineEdit.EchoMode.Password)
        return w

    def _wrap_field(self, meta: dict, widget: QWidget) -> QWidget:
        if meta.get("type") != "path":
            return widget
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self._browse(widget))
        lay.addWidget(browse)
        return wrap

    def _browse(self, widget: QWidget) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select proxy file", "", "Proxy lists (*.txt *.csv *.json);;All files (*)"
        )
        if path and isinstance(widget, QLineEdit):
            widget.setText(path)

    def result_data(self) -> dict[str, Any]:
        provider_key = self._current_provider()
        source_type = {
            "file": SourceType.FILE, "feed": SourceType.FEED, "api": SourceType.API,
            "custom": SourceType.CUSTOM, "internet": SourceType.INTERNET,
        }.get(provider_key, SourceType.CUSTOM)

        config: dict[str, Any] = {}
        for field_name, widget in self._fields.items():
            if isinstance(widget, QCheckBox):
                config[field_name] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                config[field_name] = widget.value()
            elif isinstance(widget, QPlainTextEdit):
                config[field_name] = widget.toPlainText()
            elif isinstance(widget, QComboBox):
                config[field_name] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                config[field_name] = widget.text()
        config["name"] = self.name_edit.text().strip()

        return {
            "name": self.name_edit.text().strip() or PROVIDER_LABELS.get(provider_key, provider_key),
            "provider": provider_key,
            "source_type": source_type.value,
            "config": config,
            "enabled": self.enabled_check.isChecked(),
        }
