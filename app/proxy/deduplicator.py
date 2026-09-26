"""Dedupe by protocol://host:port (credentials don't count), so the same host
from several sources collapses to one. When merging, keep whichever record
carries credentials and remember every source it came from.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.models import Endpoint, ProxyCandidate


def dedupe_endpoints(endpoints: Iterable[Endpoint]) -> list[Endpoint]:
    """Return endpoints unique by identity, preserving first-seen order.

    A later duplicate that carries credentials upgrades an earlier one that
    lacked them.
    """
    seen: dict[str, Endpoint] = {}
    for ep in endpoints:
        key = ep.identity
        existing = seen.get(key)
        if existing is None:
            seen[key] = ep
        elif not existing.has_credentials and ep.has_credentials:
            seen[key] = ep
    return list(seen.values())


def dedupe_candidates(candidates: Iterable[ProxyCandidate]) -> list[ProxyCandidate]:
    """Deduplicate candidates by endpoint identity.

    Keeps the earliest `discovered_at`; merges credentials and records all
    contributing sources in `metadata['sources']`.
    """
    seen: dict[str, ProxyCandidate] = {}
    for cand in candidates:
        key = cand.identity
        existing = seen.get(key)
        if existing is None:
            cand.metadata.setdefault("sources", [cand.source])
            seen[key] = cand
            continue
        # Merge into existing.
        sources = existing.metadata.setdefault("sources", [existing.source])
        if cand.source not in sources:
            sources.append(cand.source)
        if not existing.endpoint.has_credentials and cand.endpoint.has_credentials:
            # Upgrade endpoint with credentials.
            existing.endpoint = cand.endpoint
        if cand.discovered_at < existing.discovered_at:
            existing.discovered_at = cand.discovered_at
    return list(seen.values())


def count_duplicates(candidates: Iterable[ProxyCandidate]) -> int:
    items = list(candidates)
    return len(items) - len({c.identity for c in items})
