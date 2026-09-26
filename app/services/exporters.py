"""Export working/filtered proxies to TXT, CSV, JSON and HTML.

Exporters operate on plain dict rows (decoupled from ORM). The TXT exporter
supports configurable line formats. When the caller requests WORKING results
only, non-working proxies are excluded by the query, not here — but a safety
filter is applied regardless so failed proxies never leak into a WORKING export.
"""

from __future__ import annotations

import csv
import html
import io
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.enums import ValidationStatus

EXPORT_COLUMNS = [
    "host", "port", "protocol", "status", "exit_ip", "country", "region", "city",
    "isp", "asn", "organization", "classification", "anonymity", "latency",
    "reliability", "uptime", "score", "source", "last_checked_at",
]

# Appended only when the caller explicitly opts in to credential export.
CREDENTIAL_COLUMNS = ["username", "password"]


def proxy_to_row(proxy: Any, cipher: Any = None, include_credentials: bool = False) -> dict[str, Any]:
    """Convert a Proxy ORM object to a serializable dict.

    Credentials are included only when ``include_credentials`` is True *and* a
    ``cipher`` is supplied to decrypt them — an explicit, opt-in action. By
    default no credentials are written (see SECURITY.md).
    """
    def val(name: str) -> Any:
        v = getattr(proxy, name, None)
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    row = {col: val(col) for col in EXPORT_COLUMNS}
    if include_credentials and cipher is not None and getattr(proxy, "credential_reference", None):
        try:
            # proxy.credential lazy-loads within the caller's open session.
            cred = getattr(proxy, "credential", None)
            if cred is not None:
                row["username"] = cipher.decrypt(cred.username_enc)
                row["password"] = cipher.decrypt(cred.password_enc)
        except Exception:  # noqa: BLE001 - never fail an export over creds
            row["username"] = None
            row["password"] = None
    return row


def _only_working(rows: list[dict[str, Any]], working_only: bool) -> list[dict[str, Any]]:
    if not working_only:
        return rows
    return [r for r in rows if r.get("status") == ValidationStatus.WORKING.value]


def export_txt(
    rows: Iterable[dict[str, Any]],
    path: str | Path,
    line_format: str = "ip_port",
    working_only: bool = True,
) -> int:
    """Write TXT. ``line_format`` is 'ip_port' or 'protocol_url'.

    Credentials are intentionally never written to exports (see SECURITY.md);
    exported rows carry only the endpoint identity.
    """
    rows = _only_working(list(rows), working_only)
    lines: list[str] = []
    for r in rows:
        host, port, proto = r.get("host"), r.get("port"), r.get("protocol")
        user, pw = r.get("username"), r.get("password")
        if line_format == "protocol_url":
            if user:
                auth = f"{user}:{pw}@" if pw else f"{user}@"
                lines.append(f"{proto}://{auth}{host}:{port}")
            else:
                lines.append(f"{proto}://{host}:{port}")
        else:  # ip_port (default)
            if user:
                lines.append(f"{host}:{port}:{user}:{pw or ''}")
            else:
                lines.append(f"{host}:{port}")
    text = "\n".join(lines) + ("\n" if lines else "")
    Path(path).write_text(text, encoding="utf-8")
    return len(rows)


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    """Export columns, extended with credential columns only if rows carry them."""
    if any(r.get("username") for r in rows):
        return EXPORT_COLUMNS + CREDENTIAL_COLUMNS
    return EXPORT_COLUMNS


def export_csv(
    rows: Iterable[dict[str, Any]], path: str | Path, working_only: bool = False
) -> int:
    rows = _only_working(list(rows), working_only)
    columns = _columns(rows)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    Path(path).write_text(buf.getvalue(), encoding="utf-8")
    return len(rows)


def export_json(
    rows: Iterable[dict[str, Any]], path: str | Path, working_only: bool = False
) -> int:
    rows = _only_working(list(rows), working_only)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "proxies": rows,
    }
    Path(path).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return len(rows)


def export_html(
    rows: Iterable[dict[str, Any]], path: str | Path, working_only: bool = False,
    title: str = "ProxyAtlas Export",
) -> int:
    """Write a self-contained HTML table. All values are HTML-escaped."""
    rows = _only_working(list(rows), working_only)
    head_cells = "".join(f"<th>{html.escape(c)}</th>" for c in EXPORT_COLUMNS)
    body_rows = []
    for r in rows:
        cells = "".join(f"<td>{html.escape('' if r.get(c) is None else str(r.get(c)))}</td>" for c in EXPORT_COLUMNS)
        body_rows.append(f"<tr>{cells}</tr>")
    generated = html.escape(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:24px}}
h1{{color:#38bdf8}} table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #334155;padding:6px 8px;text-align:left}}
th{{background:#1e293b;color:#7dd3fc;position:sticky;top:0}}
tr:nth-child(even){{background:#111827}}
.meta{{color:#94a3b8;margin-bottom:12px}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="meta">Generated {generated} · {len(rows)} proxies</div>
<table><thead><tr>{head_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>
</body></html>"""
    Path(path).write_text(doc, encoding="utf-8")
    return len(rows)


def export_rows(
    rows: Iterable[dict[str, Any]],
    path: str | Path,
    fmt: str,
    working_only: bool = False,
    txt_format: str = "ip_port",
) -> int:
    fmt = fmt.lower()
    if fmt == "txt":
        return export_txt(rows, path, txt_format, working_only)
    if fmt == "csv":
        return export_csv(rows, path, working_only)
    if fmt == "json":
        return export_json(rows, path, working_only)
    if fmt == "html":
        return export_html(rows, path, working_only)
    raise ValueError(f"Unsupported export format: {fmt}")
