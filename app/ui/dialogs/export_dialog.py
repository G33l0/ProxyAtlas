"""Export configuration dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class ExportDialog(QDialog):
    def __init__(self, parent=None, default_dir: str = "", as_report: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate Report" if as_report else "Export Proxies")
        self.setMinimumWidth(480)
        self._as_report = as_report

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.format_combo = QComboBox()
        if as_report:
            self.format_combo.addItems(["html", "csv", "json", "txt"])
        else:
            self.format_combo.addItems(["txt", "csv", "json", "html"])
        self.format_combo.currentTextChanged.connect(self._sync)
        form.addRow("Format", self.format_combo)

        self.txt_format = QComboBox()
        self.txt_format.addItems(["ip_port", "protocol_url"])
        form.addRow("TXT line format", self.txt_format)

        self.working_only = QCheckBox("Working proxies only")
        self.working_only.setChecked(True)
        form.addRow("", self.working_only)

        if not as_report:
            self.include_credentials = QCheckBox("Include credentials (plaintext)")
            self.include_credentials.setChecked(False)
            form.addRow("", self.include_credentials)
            from PyQt6.QtWidgets import QLabel

            warn = QLabel(
                "Warning: writes proxy usernames/passwords in clear text to the export "
                "file. Only enable if you understand the risk and store the file "
                "securely."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#f59e0b; font-size:11px;")
            form.addRow("", warn)
        else:
            self.include_credentials = None

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        default_name = "proxyatlas_report.html" if as_report else "proxyatlas_export.txt"
        base = default_dir.rstrip("/") + "/" if default_dir else ""
        self.path_edit.setText(base + default_name)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse)
        form.addRow("Output file", path_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._sync()

    def _sync(self) -> None:
        fmt = self.format_combo.currentText()
        self.txt_format.setEnabled(fmt == "txt")
        # Update default extension.
        current = self.path_edit.text().rsplit(".", 1)[0]
        self.path_edit.setText(f"{current}.{fmt}")

    def _browse(self) -> None:
        fmt = self.format_combo.currentText()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save export", self.path_edit.text(), f"{fmt.upper()} (*.{fmt});;All files (*)"
        )
        if path:
            self.path_edit.setText(path)

    def options(self) -> dict:
        return {
            "fmt": self.format_combo.currentText(),
            "path": self.path_edit.text().strip(),
            "working_only": self.working_only.isChecked(),
            "txt_format": self.txt_format.currentText(),
            "as_report": self._as_report,
            "include_credentials": bool(
                self.include_credentials and self.include_credentials.isChecked()
            ),
        }
