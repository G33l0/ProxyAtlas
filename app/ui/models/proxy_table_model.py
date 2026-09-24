"""Database-backed proxy table model with pagination.

The model holds only the current page of rows (as detached dicts), never the
whole dataset, so the table stays responsive with very large databases. Sorting
and filtering are performed by the database via the owning page, which calls
:meth:`set_rows`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor

from app.core.enums import (
    CLASSIFICATION_LABELS,
    PROTOCOL_LABELS,
    STATUS_LABELS,
    Classification,
    Protocol,
    ValidationStatus,
)
from app.ui.theme import Palette

# (header, attribute, sort_key)
COLUMNS: list[tuple[str, str, str]] = [
    ("Status", "status", "status"),
    ("Host", "host", "host"),
    ("Port", "port", "port"),
    ("Protocol", "protocol", "protocol"),
    ("Exit IP", "exit_ip", "exit_ip"),
    ("Country", "country", "country"),
    ("Region", "region", "region"),
    ("ISP", "isp", "isp"),
    ("ASN", "asn", "asn"),
    ("Type", "classification", "classification"),
    ("Anonymity", "anonymity", "anonymity"),
    ("Latency", "latency", "latency"),
    ("Reliability", "reliability", "reliability"),
    ("Uptime", "uptime", "uptime"),
    ("Score", "score", "score"),
    ("Last Checked", "last_checked_at", "last_checked_at"),
    ("Source", "source", "source"),
]

ID_ROLE = Qt.ItemDataRole.UserRole + 1


def proxy_to_dict(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "status": p.status,
        "host": p.host,
        "port": p.port,
        "protocol": p.protocol,
        "exit_ip": p.exit_ip,
        "country": p.country,
        "region": p.region,
        "isp": p.isp,
        "asn": p.asn,
        "classification": p.classification,
        "anonymity": p.anonymity,
        "latency": p.latency,
        "reliability": p.reliability,
        "uptime": p.uptime,
        "score": p.score,
        "last_checked_at": p.last_checked_at,
        "source": p.source,
    }


class ProxyTableModel(QAbstractTableModel):
    def __init__(self, palette: Palette, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._palette = palette

    # --- population ---------------------------------------------------------
    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        if self._rows:
            top = self.index(0, 0)
            bottom = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.ForegroundRole])

    def row_dict(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def proxy_id(self, row: int) -> int | None:
        d = self.row_dict(row)
        return d["id"] if d else None

    # --- Qt model API -------------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(COLUMNS):
            return COLUMNS[section][0]
        if orientation == Qt.Orientation.Vertical:
            return section + 1
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        header, attr, _ = COLUMNS[index.column()]
        value = row.get(attr)

        if role == ID_ROLE:
            return row.get("id")

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(attr, value)

        if role == Qt.ItemDataRole.ForegroundRole:
            if attr == "status":
                return QColor(self._palette.status_color(str(value)))
            if attr == "score" and value is not None:
                return QColor(self._score_color(value))
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if attr in ("port", "latency", "reliability", "uptime", "score"):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.ToolTipRole:
            return self._display(attr, value)

        return None

    def _display(self, attr: str, value: Any) -> str:
        if value is None or value == "":
            return "—" if attr not in ("latency", "reliability", "uptime", "score") else "—"
        if attr == "status":
            return STATUS_LABELS.get(ValidationStatus.from_value(value, ValidationStatus.UNKNOWN), str(value))
        if attr == "protocol":
            return PROTOCOL_LABELS.get(Protocol.from_value(value, Protocol.HTTP), str(value).upper())
        if attr == "classification":
            return CLASSIFICATION_LABELS.get(Classification.from_value(value, Classification.UNKNOWN), str(value))
        if attr == "anonymity":
            return str(value).title()
        if attr == "latency":
            return f"{float(value):.0f} ms"
        if attr in ("reliability", "uptime"):
            return f"{float(value):.0f}%"
        if attr == "score":
            return f"{float(value):.0f}"
        if attr == "last_checked_at":
            if isinstance(value, datetime):
                return value.strftime("%Y-%m-%d %H:%M")
            return str(value)[:16]
        return str(value)

    def _score_color(self, value: float) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return self._palette.muted
        if v >= 75:
            return self._palette.success
        if v >= 45:
            return self._palette.warning
        return self._palette.error
