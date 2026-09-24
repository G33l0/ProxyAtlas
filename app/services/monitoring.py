"""Monitoring service.

Re-validates monitored targets (a saved collection filter, an ad-hoc filter, or
individual proxies) on a schedule, recording availability/latency snapshots and
updating each proxy's live status. Uses the same validation pipeline as
everything else.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.core.enums import Protocol, ValidationStatus
from app.core.models import Endpoint, ProxyCandidate
from app.database import repository as repo
from app.database.filters import FilterSpec
from app.services.app_context import AppContext
from app.services.pipeline import ProcessingPipeline
from app.testing.profiles import get_profile

logger = logging.getLogger("proxyatlas.jobs")


@dataclass
class MonitorOutcome:
    job_id: int
    total: int
    working: int
    failed: int
    avg_latency: float | None


def _resolve_endpoints(ctx: AppContext, target_type: str, target_ref: str) -> list[ProxyCandidate]:
    """Resolve a monitoring target into candidates (with credentials)."""
    candidates: list[ProxyCandidate] = []
    with ctx.database.session() as session:
        if target_type in ("collection", "filter"):
            try:
                spec = FilterSpec.from_dict(json.loads(target_ref)) if target_ref else FilterSpec()
            except (json.JSONDecodeError, TypeError):
                spec = FilterSpec()
            proxies = repo.query_proxies(session, spec, limit=5000)
        elif target_type == "proxy":
            ids = [int(x) for x in str(target_ref).split(",") if x.strip().isdigit()]
            proxies = [p for p in (repo.get_proxy(session, i) for i in ids) if p is not None]
        else:
            proxies = repo.query_proxies(session, FilterSpec().add("status", "eq", "working"), limit=5000)

        for p in proxies:
            username, password = repo.get_credentials(session, p, ctx.cipher)
            endpoint = Endpoint(
                host=p.host,
                port=p.port,
                protocol=Protocol.from_value(p.protocol, Protocol.HTTP),
                username=username,
                password=password,
            )
            candidates.append(ProxyCandidate(endpoint=endpoint, source=f"monitor:{p.source}"))
    return candidates


async def run_monitor_once(ctx: AppContext, job_id: int, target_type: str, target_ref: str) -> MonitorOutcome:
    """Run one monitoring pass for a monitoring job."""
    candidates = _resolve_endpoints(ctx, target_type, target_ref)
    if not candidates:
        with ctx.database.session() as session:
            repo.record_monitoring_result(session, job_id, 0, 0, 0, None)
        return MonitorOutcome(job_id, 0, 0, 0, None)

    profile = get_profile("quick", ctx.custom_profiles())
    pipeline = ProcessingPipeline(
        db=ctx.database,
        cipher=ctx.cipher,
        intelligence=ctx.intelligence,
        settings=ctx.testing_settings(),
        intelligence_enabled=False,  # monitoring focuses on availability
    )
    result = await pipeline.process(candidates, profile)

    avg_latency = None
    if result.stats:
        avg_latency = result.stats.get("avg_latency") or None

    with ctx.database.session() as session:
        repo.record_monitoring_result(
            session, job_id, result.total, result.working, result.failed, avg_latency
        )
    logger.info(
        "Monitor job %s: %d/%d working", job_id, result.working, result.total
    )
    return MonitorOutcome(job_id, result.total, result.working, result.failed, avg_latency)
