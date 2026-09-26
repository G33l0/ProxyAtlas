"""Advanced filter bar producing a `FilterSpec`."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from app.core.enums import Anonymity, Classification, Protocol, ValidationStatus
from app.database.filters import FilterSpec


class FilterBar(QWidget):
    """Builds a FilterSpec from user controls."""

    applied = pyqtSignal(object)   # FilterSpec
    cleared = pyqtSignal()
    save_requested = pyqtSignal(object)  # FilterSpec
    load_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search host, exit IP, ISP, country, ASN...")
        self.search.returnPressed.connect(self._emit_apply)

        self.protocol = self._combo(["Any protocol"] + [p.value.upper() for p in Protocol])
        self.status = self._combo(["Any status"] + [s.value for s in ValidationStatus])
        self.classification = self._combo(["Any type"] + [c.value for c in Classification])
        self.anonymity = self._combo(["Any anonymity"] + [a.value for a in Anonymity])

        self.country = QLineEdit()
        self.country.setPlaceholderText("Country code (e.g. US)")
        self.country.setMaximumWidth(150)

        self.min_score = self._spin("Min score", 0, 100)
        self.max_latency = self._spin("Max latency ms", 0, 60000, step=50)
        self.min_reliability = self._spin("Min reliability %", 0, 100)

        self.combine = self._combo(["Match ALL (AND)", "Match ANY (OR)"])

        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(self._emit_apply)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        save_btn = QPushButton("Save Filter")
        save_btn.clicked.connect(lambda: self.save_requested.emit(self.build_spec()))
        load_btn = QPushButton("Load Filter")
        load_btn.clicked.connect(self.load_requested.emit)

        grid.addWidget(self.search, 0, 0, 1, 4)
        grid.addWidget(self.combine, 0, 4)
        grid.addWidget(apply_btn, 0, 5)
        grid.addWidget(self.protocol, 1, 0)
        grid.addWidget(self.status, 1, 1)
        grid.addWidget(self.classification, 1, 2)
        grid.addWidget(self.anonymity, 1, 3)
        grid.addWidget(self.country, 1, 4)
        grid.addWidget(clear_btn, 1, 5)
        grid.addWidget(self._labeled("Min score", self.min_score), 2, 0)
        grid.addWidget(self._labeled("Max latency (ms)", self.max_latency), 2, 1)
        grid.addWidget(self._labeled("Min reliability (%)", self.min_reliability), 2, 2)
        grid.addWidget(save_btn, 2, 4)
        grid.addWidget(load_btn, 2, 5)

    def _combo(self, items: list[str]) -> QComboBox:
        c = QComboBox()
        c.addItems(items)
        return c

    def _spin(self, _tip: str, lo: int, hi: int, step: int = 1) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(0)
        s.setDecimals(0)
        return s

    def _labeled(self, text: str, widget: QWidget) -> QWidget:
        wrap = QWidget()
        from PyQt6.QtWidgets import QHBoxLayout

        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lbl = QLabel(text)
        lbl.setObjectName("StatLabel")
        lay.addWidget(lbl)
        lay.addWidget(widget)
        return wrap

    # --- spec building ------------------------------------------------------
    def build_spec(self) -> FilterSpec:
        spec = FilterSpec()
        spec.combine = "or" if self.combine.currentIndex() == 1 else "and"
        if self.search.text().strip():
            spec.search = self.search.text().strip()
        if self.protocol.currentIndex() > 0:
            spec.add("protocol", "eq", self.protocol.currentText().lower())
        if self.status.currentIndex() > 0:
            spec.add("status", "eq", self.status.currentText())
        if self.classification.currentIndex() > 0:
            spec.add("classification", "eq", self.classification.currentText())
        if self.anonymity.currentIndex() > 0:
            spec.add("anonymity", "eq", self.anonymity.currentText())
        if self.country.text().strip():
            spec.add("country_code", "eq", self.country.text().strip().upper())
        if self.min_score.value() > 0:
            spec.add("score", "gte", self.min_score.value())
        if self.max_latency.value() > 0:
            spec.add("latency", "lte", self.max_latency.value())
        if self.min_reliability.value() > 0:
            spec.add("reliability", "gte", self.min_reliability.value())
        return spec

    def load_spec(self, spec: FilterSpec) -> None:
        """Populate controls from a spec (best effort)."""
        self._clear(emit=False)
        self.combine.setCurrentIndex(1 if spec.combine == "or" else 0)
        self.search.setText(spec.search or "")
        for cond in spec.conditions:
            if cond.field == "protocol":
                self._set_combo(self.protocol, str(cond.value).upper())
            elif cond.field == "status":
                self._set_combo(self.status, str(cond.value))
            elif cond.field == "classification":
                self._set_combo(self.classification, str(cond.value))
            elif cond.field == "anonymity":
                self._set_combo(self.anonymity, str(cond.value))
            elif cond.field == "country_code":
                self.country.setText(str(cond.value))
            elif cond.field == "score":
                self.min_score.setValue(float(cond.value))
            elif cond.field == "latency":
                self.max_latency.setValue(float(cond.value))
            elif cond.field == "reliability":
                self.min_reliability.setValue(float(cond.value))
        self._emit_apply()

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        idx = combo.findText(value, )
        if idx < 0:
            idx = combo.findText(value.lower())
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _emit_apply(self) -> None:
        self.applied.emit(self.build_spec())

    def _clear(self, emit: bool = True) -> None:
        self.search.clear()
        self.country.clear()
        for combo in (self.protocol, self.status, self.classification, self.anonymity, self.combine):
            combo.setCurrentIndex(0)
        for spin in (self.min_score, self.max_latency, self.min_reliability):
            spin.setValue(0)
        if emit:
            self.cleared.emit()
