"""0-100 quality score from weighted parts the UI can show individually:
connectivity (did it work), latency (log-scaled), reliability (success rate),
stability (recent consistency) and freshness (how recently it worked).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.core.enums import ValidationStatus
from app.core.models import QualityScore

WEIGHTS = {
    "connectivity": 0.30,
    "latency": 0.20,
    "reliability": 0.25,
    "stability": 0.15,
    "freshness": 0.10,
}


def _latency_score(latency_ms: float | None) -> float:
    """Map latency to 0-100. <=100ms -> ~100, 3000ms -> ~0."""
    if latency_ms is None or latency_ms <= 0:
        return 0.0
    if latency_ms <= 100:
        return 100.0
    # Logarithmic falloff between 100ms and 3000ms.
    score = 100.0 * (1 - (math.log10(latency_ms / 100.0) / math.log10(30.0)))
    return max(0.0, min(100.0, score))


def _freshness_score(last_success_at: datetime | None) -> float:
    if last_success_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    if last_success_at.tzinfo is None:
        last_success_at = last_success_at.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (now - last_success_at).total_seconds() / 3600.0)
    if age_hours <= 1:
        return 100.0
    if age_hours >= 24 * 7:  # a week old -> stale
        return 5.0
    # Linear-ish decay across a week.
    return max(5.0, 100.0 * (1 - age_hours / (24 * 7)))


def _stability_score(success_count: int, failure_count: int, samples: int, successes: int) -> float:
    """Consistency: penalize mixed histories and single-sample runs less."""
    total = success_count + failure_count
    if total == 0 and samples == 0:
        return 0.0
    # Recent-run consistency (from repeated_requests in deep profiles).
    recent = (successes / samples * 100.0) if samples else 0.0
    # Historical consistency.
    historical = (success_count / total * 100.0) if total else recent
    # Weight recent slightly more.
    return round(0.6 * recent + 0.4 * historical, 2) if samples > 1 else round(historical, 2)


def compute_quality(
    *,
    status: ValidationStatus | str,
    latency_ms: float | None,
    reliability: float,
    success_count: int = 0,
    failure_count: int = 0,
    samples: int = 1,
    successes: int = 0,
    last_success_at: datetime | None = None,
) -> QualityScore:
    """Return an explainable composite quality score."""
    status_val = status.value if isinstance(status, ValidationStatus) else str(status)
    connectivity = 100.0 if status_val == ValidationStatus.WORKING.value else 0.0
    latency = _latency_score(latency_ms)
    reliability = max(0.0, min(100.0, float(reliability)))
    stability = _stability_score(success_count, failure_count, samples, successes)
    freshness = _freshness_score(last_success_at)

    components = {
        "connectivity": round(connectivity, 1),
        "latency": round(latency, 1),
        "reliability": round(reliability, 1),
        "stability": round(stability, 1),
        "freshness": round(freshness, 1),
    }
    score = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
    # A non-working proxy is capped low regardless of stale metrics.
    if connectivity == 0.0:
        score = min(score, 20.0)
    return QualityScore(score=round(score, 1), components=components)
