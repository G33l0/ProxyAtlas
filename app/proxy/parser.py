"""Parse the proxy formats you actually see in the wild: IP:PORT,
IP:PORT:USER:PASS, PROTO://IP:PORT, PROTO://USER:PASS@IP:PORT, bracketed IPv6
and hostnames. Bad input raises ParseError (and only ParseError); nothing is
ever executed.
"""

from __future__ import annotations

import ipaddress
import re

from app.core.enums import Protocol
from app.core.exceptions import ParseError
from app.core.models import Endpoint

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)

_PROTOCOL_ALIASES = {
    "http": Protocol.HTTP,
    "https": Protocol.HTTPS,
    "socks4": Protocol.SOCKS4,
    "socks4a": Protocol.SOCKS4,
    "socks5": Protocol.SOCKS5,
    "socks5h": Protocol.SOCKS5,
    "socks": Protocol.SOCKS5,
}


def _valid_port(value: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ParseError(f"Invalid port: {value!r}") from exc
    if not (1 <= port <= 65535):
        raise ParseError(f"Port out of range: {port}")
    return port


def _valid_host(host: str) -> str:
    host = host.strip()
    if not host:
        raise ParseError("Empty host")
    # IPv4/IPv6 literal (may include brackets already stripped by caller)
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    # A dotted all-numeric token is an IP address, not a hostname - reject it
    # if it is not a valid one (e.g. 999.999.999.999) rather than treating it
    # as a hostname.
    labels = host.split(".")
    if len(labels) == 4 and all(label.isdigit() for label in labels):
        raise ParseError(f"Invalid IPv4 address: {host!r}")
    if _HOSTNAME_RE.match(host):
        return host.lower()
    raise ParseError(f"Invalid host: {host!r}")


def _split_hostport(text: str) -> tuple[str, str]:
    """Split `host:port` handling bracketed IPv6."""
    text = text.strip()
    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            raise ParseError(f"Unterminated IPv6 literal: {text!r}")
        host = text[1:end]
        rest = text[end + 1 :]
        if not rest.startswith(":"):
            raise ParseError(f"Missing port for IPv6 host: {text!r}")
        return host, rest[1:]
    # Ambiguous bare IPv6 without brackets but with a port is unsupported;
    # require exactly one colon for host:port.
    if text.count(":") > 1:
        # Could be an unbracketed IPv6 with no port -> invalid for endpoint.
        raise ParseError(f"Ambiguous host:port (bracket IPv6): {text!r}")
    if ":" not in text:
        raise ParseError(f"Missing port: {text!r}")
    host, port = text.rsplit(":", 1)
    return host, port


def parse_proxy(
    raw: str,
    default_protocol: Protocol = Protocol.HTTP,
) -> Endpoint:
    """Parse a single proxy record into an `Endpoint`.

    Raises `ParseError` on malformed input.
    """
    if raw is None:
        raise ParseError("None is not a proxy record")
    text = raw.strip()
    if not text or text.startswith("#") or text.startswith(";"):
        raise ParseError("Empty or comment line")

    # Strip surrounding quotes / trailing commas that appear in CSV/JSON dumps.
    text = text.strip().strip(",").strip().strip('"').strip("'").strip()

    protocol: Protocol | None = None
    username: str | None = None
    password: str | None = None

    # 1. Scheme prefix
    if "://" in text:
        scheme, _, remainder = text.partition("://")
        proto = _PROTOCOL_ALIASES.get(scheme.strip().lower())
        if proto is None:
            raise ParseError(f"Unsupported protocol scheme: {scheme!r}")
        protocol = proto
        text = remainder

    # 2. Credentials via user:pass@host
    if "@" in text:
        creds, _, hostpart = text.rpartition("@")
        if ":" in creds:
            username, _, password = creds.partition(":")
        else:
            username = creds
        username = username or None
        password = password or None
        text = hostpart

    # 3. Now text is host:port  OR  host:port:user:pass (colon form)
    #    Only treat the colon-credential form when there is no scheme/@ creds
    #    and exactly 3 colons on an IPv4/hostname.
    if username is None and text.count(":") == 3 and not text.startswith("["):
        host, port, username, password = text.split(":")
        username = username or None
        password = password or None
        host = _valid_host(host)
        return Endpoint(
            host=host,
            port=_valid_port(port),
            protocol=protocol or default_protocol,
            username=username,
            password=password,
        )

    host, port = _split_hostport(text)
    host = _valid_host(host)
    return Endpoint(
        host=host,
        port=_valid_port(port),
        protocol=protocol or default_protocol,
        username=username,
        password=password,
    )


def parse_many(
    lines: list[str],
    default_protocol: Protocol = Protocol.HTTP,
) -> tuple[list[Endpoint], list[tuple[str, str]]]:
    """Parse many records.

    Returns `(endpoints, errors)` where errors is a list of
    `(raw_line, message)` for records that failed. Never raises.
    """
    endpoints: list[Endpoint] = []
    errors: list[tuple[str, str]] = []
    for line in lines:
        raw = (line or "").strip()
        if not raw or raw.startswith("#") or raw.startswith(";"):
            continue
        try:
            endpoints.append(parse_proxy(raw, default_protocol))
        except ParseError as exc:
            errors.append((raw, str(exc)))
    return endpoints, errors
