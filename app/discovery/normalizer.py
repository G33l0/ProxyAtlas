"""Normalization utilities bridging raw text/records into candidates."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from datetime import datetime, timezone

from app.core.enums import Protocol, ValidationStatus
from app.core.models import Endpoint, ProxyCandidate
from app.proxy.parser import parse_proxy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def candidate_from_endpoint(
    endpoint: Endpoint, source: str, source_reference: str | None = None
) -> ProxyCandidate:
    return ProxyCandidate(
        endpoint=endpoint,
        source=source,
        source_reference=source_reference,
        discovered_at=_now(),
        validation_status=ValidationStatus.DISCOVERED,
    )


def normalize_lines(
    lines: Iterable[str],
    source: str,
    default_protocol: Protocol = Protocol.HTTP,
    source_reference: str | None = None,
) -> tuple[list[ProxyCandidate], list[tuple[str, str]]]:
    candidates: list[ProxyCandidate] = []
    errors: list[tuple[str, str]] = []
    for line in lines:
        raw = (line or "").strip()
        if not raw or raw.startswith("#") or raw.startswith(";"):
            continue
        try:
            ep = parse_proxy(raw, default_protocol)
        except Exception as exc:  # noqa: BLE001 - parser raises ParseError
            errors.append((raw, str(exc)))
            continue
        cand = candidate_from_endpoint(ep, source, source_reference)
        cand.raw = raw
        candidates.append(cand)
    return candidates, errors


def normalize_csv(
    text: str, source: str, default_protocol: Protocol = Protocol.HTTP
) -> tuple[list[ProxyCandidate], list[tuple[str, str]]]:
    """Parse CSV where columns may be host,port[,protocol[,user,pass]] or a
    single proxy string per row."""
    candidates: list[ProxyCandidate] = []
    errors: list[tuple[str, str]] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row:
            continue
        cells = [c.strip() for c in row if c is not None]
        if not cells or cells[0].startswith("#"):
            continue
        try:
            raw = _row_to_proxy_string(cells)
            ep = parse_proxy(raw, default_protocol)
            candidates.append(candidate_from_endpoint(ep, source))
        except Exception as exc:  # noqa: BLE001 - skip header/malformed rows
            errors.append((",".join(cells), str(exc)))
    return candidates, errors


def _row_to_proxy_string(cells: list[str]) -> str:
    # Header row detection.
    lowered = [c.lower() for c in cells]
    if "host" in lowered or "ip" in lowered or "proxy" in lowered:
        raise ValueError("header row")
    if len(cells) == 1:
        return cells[0]
    if len(cells) == 2:
        return f"{cells[0]}:{cells[1]}"
    # host, port, protocol, [user, pass]
    host, port = cells[0], cells[1]
    proto = cells[2] if len(cells) >= 3 and not cells[2].isdigit() else None
    creds = ""
    if len(cells) >= 5:
        creds = f":{cells[3]}:{cells[4]}"
    base = f"{host}:{port}{creds}"
    return f"{proto}://{base}" if proto else base


def normalize_json(
    text: str, source: str, default_protocol: Protocol = Protocol.HTTP
) -> tuple[list[ProxyCandidate], list[tuple[str, str]]]:
    """Parse JSON: a list of strings, or list of objects with host/port keys."""
    candidates: list[ProxyCandidate] = []
    errors: list[tuple[str, str]] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [(text[:60], f"Invalid JSON: {exc}")]

    records = data if isinstance(data, list) else data.get("proxies", []) if isinstance(data, dict) else []
    for rec in records:
        try:
            if isinstance(rec, str):
                ep = parse_proxy(rec, default_protocol)
            elif isinstance(rec, dict):
                ep = _endpoint_from_dict(rec, default_protocol)
            else:
                errors.append((str(rec)[:60], "Unsupported record type"))
                continue
            candidates.append(candidate_from_endpoint(ep, source))
        except Exception as exc:  # noqa: BLE001
            errors.append((str(rec)[:60], str(exc)))
    return candidates, errors


def _endpoint_from_dict(rec: dict, default_protocol: Protocol) -> Endpoint:
    host = rec.get("host") or rec.get("ip") or rec.get("address")
    port = rec.get("port")
    if not host or not port:
        # Maybe a full string under 'proxy'.
        if rec.get("proxy"):
            return parse_proxy(str(rec["proxy"]), default_protocol)
        raise ValueError("missing host/port")
    proto = rec.get("protocol") or rec.get("type") or default_protocol.value
    user = rec.get("username") or rec.get("user")
    pw = rec.get("password") or rec.get("pass")
    # Build the Endpoint from validated fields directly. Reconstructing a URL
    # string and re-parsing it would corrupt credentials that contain ':' or
    # '@', so only host:port goes through the parser.
    endpoint = parse_proxy(f"{proto}://{host}:{port}", default_protocol)
    if user:
        endpoint = Endpoint(
            host=endpoint.host,
            port=endpoint.port,
            protocol=endpoint.protocol,
            username=str(user),
            password=str(pw) if pw is not None else None,
        )
    return endpoint
