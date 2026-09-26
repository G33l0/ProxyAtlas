"""Guess a proxy's anonymity from the headers a judge endpoint (httpbin /get)
echoes back plus our own public IP. We record the evidence and don't claim
certainty the headers can't support.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.enums import Anonymity

# Headers that reveal a proxy is in use.
_PROXY_HEADERS = [
    "via",
    "x-forwarded-for",
    "forwarded",
    "x-forwarded",
    "x-real-ip",
    "proxy-connection",
    "x-proxy-id",
    "client-ip",
]


def analyze_anonymity(
    echoed_headers: dict[str, str],
    exit_ip: str | None,
    real_ip: str | None,
) -> tuple[Anonymity, dict[str, Any]]:
    """Return an `Anonymity` level and supporting evidence.

    * `TRANSPARENT`  - the client's real IP is exposed.
    * `ANONYMOUS`    - proxy headers present but real IP hidden.
    * `ELITE`        - no proxy headers and real IP hidden.
    * `UNKNOWN`      - insufficient signal.
    """
    normalized = {k.lower(): v for k, v in echoed_headers.items()}
    evidence: dict[str, Any] = {"proxy_headers": [], "real_ip_leaked": False}

    found_proxy_headers = [h for h in _PROXY_HEADERS if h in normalized and normalized[h]]
    evidence["proxy_headers"] = found_proxy_headers

    real_ip_leaked = False
    if real_ip:
        # Tokenize header values on non-IP characters so we match the real IP as
        # a whole address, not as a substring of an unrelated value (e.g.
        # '11.2.3.44' must not match '1.2.3.4').
        blob = " ".join(str(v) for v in normalized.values())
        tokens = set(re.split(r"[^0-9a-fA-F:.]+", blob))
        if real_ip in tokens:
            real_ip_leaked = True
        if exit_ip and real_ip == exit_ip:
            # Exit equals our real IP -> effectively no anonymity.
            real_ip_leaked = True
    evidence["real_ip_leaked"] = real_ip_leaked

    if not exit_ip:
        return Anonymity.UNKNOWN, evidence

    if real_ip_leaked:
        return Anonymity.TRANSPARENT, evidence
    if found_proxy_headers:
        return Anonymity.ANONYMOUS, evidence
    if real_ip is None:
        # We could not establish the baseline; be honest.
        evidence["note"] = "No real-IP baseline; cannot confirm elite"
        return Anonymity.ANONYMOUS if not found_proxy_headers else Anonymity.UNKNOWN, evidence
    return Anonymity.ELITE, evidence
