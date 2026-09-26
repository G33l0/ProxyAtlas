"""Discovery-stage deduplication.

Wraps `app.proxy.deduplicator` for candidate batches and adds a helper to
drop candidates whose identity already exists in the discovery queue / main DB.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.models import ProxyCandidate
from app.proxy.deduplicator import dedupe_candidates as _dedupe


def dedupe_batch(candidates: Iterable[ProxyCandidate]) -> list[ProxyCandidate]:
    return _dedupe(candidates)


def filter_known(
    candidates: Iterable[ProxyCandidate], known_identities: set[str]
) -> tuple[list[ProxyCandidate], int]:
    """Return (new_candidates, skipped_count) against a set of known ids."""
    new: list[ProxyCandidate] = []
    skipped = 0
    for cand in candidates:
        if cand.identity in known_identities:
            skipped += 1
        else:
            new.append(cand)
    return new, skipped
