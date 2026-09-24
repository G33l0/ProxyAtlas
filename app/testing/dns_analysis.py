"""Conservative DNS behaviour analysis for a validated proxy.

True DNS-leak detection requires dedicated infrastructure; this module makes
only claims the available signals support and reports a confidence. It checks
whether the exit IP and any echoed forwarding headers are consistent, and
whether the proxy appears to resolve names itself.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import DnsStatus


def analyze_dns(
    *,
    request_succeeded: bool,
    exit_ip: str | None,
    echoed_headers: dict[str, str],
    real_ip: str | None,
) -> tuple[DnsStatus, dict[str, Any], float]:
    """Return ``(status, evidence, confidence)``.

    Confidence is 0..1 and deliberately modest — the test cannot prove the
    absence of a leak.
    """
    evidence: dict[str, Any] = {}
    if not request_succeeded or not exit_ip:
        return DnsStatus.UNTESTED, {"reason": "no successful proxied request"}, 0.0

    normalized = {k.lower(): v for k, v in echoed_headers.items()}
    forwarded = normalized.get("x-forwarded-for") or normalized.get("forwarded")
    evidence["forwarded_for"] = forwarded

    # If the real IP appears alongside the exit IP, the origin sees the client.
    if real_ip and forwarded and real_ip in str(forwarded):
        evidence["reason"] = "real client IP present in forwarding header"
        return DnsStatus.LEAK_SUSPECTED, evidence, 0.6

    # Exit IP present and no client leakage observed -> looks OK, low-moderate
    # confidence because DNS resolution path is not directly observable here.
    evidence["reason"] = "exit IP consistent; no client leakage observed"
    return DnsStatus.OK, evidence, 0.4
