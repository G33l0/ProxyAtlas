"""FilterSpec: a serializable set of conditions the repository turns into
SQLAlchemy expressions. One filter language for the UI, collections and exports,
combined with AND or OR.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.database.models import Proxy

# Map of filter field -> ORM column and supported operators.
_TEXT_FIELDS = {
    "host": Proxy.host,
    "exit_ip": Proxy.exit_ip,
    "country": Proxy.country,
    "country_code": Proxy.country_code,
    "region": Proxy.region,
    "city": Proxy.city,
    "isp": Proxy.isp,
    "asn": Proxy.asn,
    "organization": Proxy.organization,
    "source": Proxy.source,
    "tags": Proxy.tags,
}
_ENUM_FIELDS = {
    "protocol": Proxy.protocol,
    "classification": Proxy.classification,
    "anonymity": Proxy.anonymity,
    "status": Proxy.status,
    "dns_status": Proxy.dns_status,
}
_NUMERIC_FIELDS = {
    "latency": Proxy.latency,
    "reliability": Proxy.reliability,
    "stability": Proxy.stability,
    "uptime": Proxy.uptime,
    "score": Proxy.score,
    "port": Proxy.port,
}
_DATE_FIELDS = {
    "discovered_at": Proxy.discovered_at,
    "last_checked_at": Proxy.last_checked_at,
}

VALID_OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "contains", "in", "before", "after"}


@dataclass
class Condition:
    field: str
    op: str
    value: Any

    def to_expression(self) -> ColumnElement[bool] | None:
        op = self.op
        if op not in VALID_OPERATORS:
            return None

        if self.field in _TEXT_FIELDS:
            col = _TEXT_FIELDS[self.field]
            if op == "contains":
                return col.ilike(f"%{self.value}%")
            if op == "eq":
                return col == self.value
            if op == "ne":
                return col != self.value
            if op == "in" and isinstance(self.value, (list, tuple)):
                return col.in_(list(self.value))
            return None

        if self.field in _ENUM_FIELDS:
            col = _ENUM_FIELDS[self.field]
            val = str(self.value).lower() if self.value is not None else self.value
            if op == "eq":
                return col == val
            if op == "ne":
                return col != val
            if op == "in" and isinstance(self.value, (list, tuple)):
                return col.in_([str(v).lower() for v in self.value])
            return None

        if self.field in _NUMERIC_FIELDS:
            col = _NUMERIC_FIELDS[self.field]
            try:
                num = float(self.value)
            except (TypeError, ValueError):
                return None
            return {
                "eq": col == num,
                "ne": col != num,
                "lt": col < num,
                "lte": col <= num,
                "gt": col > num,
                "gte": col >= num,
            }.get(op)

        if self.field in _DATE_FIELDS:
            col = _DATE_FIELDS[self.field]
            if op in ("before", "lt", "lte"):
                return col <= self.value
            if op in ("after", "gt", "gte"):
                return col >= self.value
            if op == "eq":
                return col == self.value
            return None

        return None


@dataclass
class FilterSpec:
    """A collection of conditions combined with AND or OR, plus a search term."""

    conditions: list[Condition] = field(default_factory=list)
    combine: str = "and"  # "and" | "or"
    search: str | None = None  # free-text across host/exit_ip/isp/country

    def add(self, field_name: str, op: str, value: Any) -> FilterSpec:
        self.conditions.append(Condition(field_name, op, value))
        return self

    def to_expression(self) -> ColumnElement[bool] | None:
        exprs = [c.to_expression() for c in self.conditions]
        exprs = [e for e in exprs if e is not None]

        if self.search:
            term = f"%{self.search.strip()}%"
            exprs_search = or_(
                Proxy.host.ilike(term),
                Proxy.exit_ip.ilike(term),
                Proxy.isp.ilike(term),
                Proxy.country.ilike(term),
                Proxy.organization.ilike(term),
                Proxy.asn.ilike(term),
            )
        else:
            exprs_search = None

        if not exprs and exprs_search is None:
            return None

        combined: ColumnElement[bool] | None
        if exprs:
            combined = or_(*exprs) if self.combine == "or" else and_(*exprs)
        else:
            combined = None

        if combined is not None and exprs_search is not None:
            return and_(combined, exprs_search)
        return combined if combined is not None else exprs_search

    # Serialization ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "conditions": [asdict(c) for c in self.conditions],
            "combine": self.combine,
            "search": self.search,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterSpec:
        conditions = [
            Condition(c["field"], c["op"], c.get("value"))
            for c in data.get("conditions", [])
        ]
        return cls(
            conditions=conditions,
            combine=data.get("combine", "and"),
            search=data.get("search"),
        )
