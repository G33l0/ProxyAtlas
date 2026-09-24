"""Collections page: saved filter definitions."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
)

from app.database import repository as repo
from app.database.filters import FilterSpec
from app.ui.pages.base import BasePage
from app.ui.pages.proxies import QUICK_FILTERS
from app.ui.widgets.common import Card, EmptyState


class CollectionDialog(QDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Collection")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.base = QComboBox()
        for label, spec in QUICK_FILTERS:
            self.base.addItem(label, spec)
        self.protocol = QComboBox()
        self.protocol.addItems(["Any", "http", "https", "socks4", "socks5"])
        self.country = QLineEdit()
        self.country.setPlaceholderText("Country code, e.g. US")
        self.min_score = QLineEdit()
        self.min_score.setPlaceholderText("Minimum score (optional)")
        form.addRow("Name", self.name)
        form.addRow("Base filter", self.base)
        form.addRow("Protocol", self.protocol)
        form.addRow("Country", self.country)
        form.addRow("Min score", self.min_score)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def build(self) -> tuple[str, FilterSpec]:
        base = self.base.currentData()
        spec = FilterSpec.from_dict(base.to_dict())
        if self.protocol.currentIndex() > 0:
            spec.add("protocol", "eq", self.protocol.currentText())
        if self.country.text().strip():
            spec.add("country_code", "eq", self.country.text().strip().upper())
        if self.min_score.text().strip():
            try:
                spec.add("score", "gte", float(self.min_score.text().strip()))
            except ValueError:
                pass
        return self.name.text().strip(), spec


class CollectionsPage(BasePage):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx, main_window, "Collections", "Saved filter definitions for quick access")

        toolbar = QHBoxLayout()
        for label, slot, primary in [
            ("New Collection", self._new, True), ("Open in Proxies", self._open, False),
            ("Delete", self._delete, False), ("Refresh", self.refresh, False),
        ]:
            b = QPushButton(label)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(slot)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        self.root.addLayout(toolbar)

        self.stack = QStackedWidget()
        card = Card()
        from PyQt6.QtWidgets import QVBoxLayout

        cl = QVBoxLayout(card)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Matches", "Definition"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._open)
        cl.addWidget(self.table)
        self.stack.addWidget(card)
        self.empty = EmptyState("No collections yet.\nCreate a collection to save a filter for reuse.")
        self.stack.addWidget(self.empty)
        self.root.addWidget(self.stack, 1)

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        with self.ctx.database.session() as session:
            self._collections = repo.list_collections(session)
            rows = []
            for c in self._collections:
                spec = FilterSpec.from_dict(c["filter"])
                count = repo.count_proxies(session, spec)
                rows.append((c["name"], count, self._describe(spec)))
        self.table.setRowCount(len(rows))
        for i, (name, count, desc) in enumerate(rows):
            item = QTableWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.table.setItem(i, 0, item)
            self.table.setItem(i, 1, QTableWidgetItem(str(count)))
            self.table.setItem(i, 2, QTableWidgetItem(desc))
        self.stack.setCurrentWidget(self.empty if not rows else self.stack.widget(0))

    def _describe(self, spec: FilterSpec) -> str:
        parts = [f"{c.field} {c.op} {c.value}" for c in spec.conditions]
        if spec.search:
            parts.append(f"search~{spec.search}")
        return f" {spec.combine.upper()} ".join(parts) if parts else "All proxies"

    def _selected_name(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def _new(self) -> None:
        dlg = CollectionDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, spec = dlg.build()
        if not name:
            self.toast("Enter a collection name", "warning")
            return
        with self.ctx.database.session() as session:
            repo.save_collection(session, name, spec)
        self.toast(f"Collection '{name}' saved", "success")
        self.refresh()

    def _open(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        col = next((c for c in self._collections if c["name"] == name), None)
        if col:
            self.main.open_proxies_with_filter(FilterSpec.from_dict(col["filter"]))

    def _delete(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if QMessageBox.question(self, "Delete", f"Delete collection '{name}'?") != QMessageBox.StandardButton.Yes:
            return
        with self.ctx.database.session() as session:
            repo.delete_collection(session, name)
        self.refresh()
