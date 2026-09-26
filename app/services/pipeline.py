"""Validation → intelligence → classification → quality → database pipeline.

This is the orchestration heart of ProxyAtlas. Given a batch of candidates it:

1. Runs the concurrent validation engine (real proxied requests).
2. Enriches successful proxies with IP intelligence (bounded concurrency).
3. Classifies them from evidence and computes an explainable quality score.
4. Persists everything to the database in batched transactions.

It is fully async and driven by the Qt workers; it never touches Qt itself.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.core.models import ProxyCandidate, ValidationResult
from app.database import repository as repo
from app.database.engine import Database
from app.intelligence.classification import classifier
from app.intelligence.manager import IntelligenceManager
from app.proxy.quality import compute_quality
from app.testing.engine import JobControl, ValidationEngine
from app.testing.profiles import ValidationProfile

logger = logging.getLogger("proxyatlas.jobs")


@dataclass
class PipelineResult:
    total: int = 0
    working: int = 0
    failed: int = 0
    persisted: int = 0
    stats: dict | None = None


class ProcessingPipeline:
    def __init__(
        self,
        db: Database,
        cipher,
        intelligence: IntelligenceManager,
        settings: dict,
        intelligence_enabled: bool = True,
    ) -> None:
        self.db = db
        self.cipher = cipher
        self.intelligence = intelligence
        self.settings = settings
        self.intelligence_enabled = intelligence_enabled

    async def process(
        self,
        candidates: Iterable[ProxyCandidate],
        profile: ValidationProfile,
        control: JobControl | None = None,
        on_progress: Callable[[dict], None] | None = None,
        on_result: Callable[[ValidationResult], None] | None = None,
        concurrency: int | None = None,
    ) -> PipelineResult:
        candidates = list(candidates)
        by_identity = {c.identity: c for c in candidates}
        # Fallback lookup ignoring protocol, so a candidate whose protocol was
        # corrected by auto-detection still maps back to its original source.
        by_hostport = {(c.endpoint.host, c.endpoint.port): c for c in candidates}
        endpoints = [c.endpoint for c in candidates]

        val_endpoints = self.settings.get("validation_endpoints") or []
        judge = self.settings.get("judge_endpoint")
        conc = concurrency or int(self.settings.get("concurrency", 40))
        retries = int(self.settings.get("retries", 0) or 0)
        retry_backoff = float(self.settings.get("retry_backoff", 0.0) or 0.0)
        autodetect = bool(self.settings.get("protocol_autodetect", False))

        engine = ValidationEngine(
            profile=profile,
            validation_endpoints=val_endpoints,
            judge_endpoint=judge,
            concurrency=conc,
            control=control,
            retries=retries,
            retry_backoff=retry_backoff,
            autodetect_protocols=autodetect,
        )

        results = await engine.run(endpoints, on_result=on_result, on_progress=on_progress)

        # Enrich working proxies with intelligence (bounded concurrency).
        intel_map: dict[str, object] = {}
        if self.intelligence_enabled:
            sem = asyncio.Semaphore(min(10, conc))

            async def enrich(res: ValidationResult) -> None:
                if not res.ok or not res.exit_ip:
                    return
                async with sem:
                    try:
                        intel_map[res.endpoint.identity] = await self.intelligence.lookup(res.exit_ip)
                    except Exception as exc:  # noqa: BLE001 - non-fatal
                        logger.warning("Intelligence enrichment failed: %s", exc)

            await asyncio.gather(*(enrich(r) for r in results), return_exceptions=True)

        # Persist in one transaction.
        persisted = 0
        working = 0
        failed = 0
        with self.db.session() as session:
            for res in results:
                cand = by_identity.get(res.endpoint.identity)
                if cand is None:
                    original = by_hostport.get((res.endpoint.host, res.endpoint.port))
                    # Auto-detection corrected the protocol: adopt the detected
                    # one, preserve the original source, and remove any stale
                    # row that still carries the mislabeled protocol so the same
                    # host:port never appears twice.
                    cand = ProxyCandidate(
                        endpoint=res.endpoint,
                        source=original.source if original else "validation",
                    )
                    repo.delete_proxies_at_hostport_except(
                        session, res.endpoint.host, res.endpoint.port, res.endpoint.protocol.value
                    )
                proxy = repo.upsert_proxy_from_candidate(session, cand, self.cipher)
                repo.apply_validation_result(session, proxy, res, profile.name)

                if res.ok:
                    working += 1
                    intel = intel_map.get(res.endpoint.identity)
                    if intel is not None:
                        repo.apply_intelligence(session, proxy, intel)
                        repo.cache_geo(session, intel)
                        repo.cache_network(session, intel)
                        cls = classifier.classify(intel)
                        repo.apply_classification(session, proxy, cls)
                    quality = compute_quality(
                        status=res.status,
                        latency_ms=res.latency_ms,
                        reliability=proxy.reliability,
                        success_count=proxy.success_count,
                        failure_count=proxy.failure_count,
                        samples=res.samples,
                        successes=res.successes,
                        last_success_at=proxy.last_success_at,
                    )
                    repo.apply_quality(session, proxy, quality)
                else:
                    failed += 1
                    # Recompute a (low) score so failed proxies rank correctly.
                    quality = compute_quality(
                        status=res.status,
                        latency_ms=proxy.latency,
                        reliability=proxy.reliability,
                        success_count=proxy.success_count,
                        failure_count=proxy.failure_count,
                        last_success_at=proxy.last_success_at,
                    )
                    repo.apply_quality(session, proxy, quality)
                persisted += 1

            repo.add_audit(session, "validation_batch", f"{persisted} proxies processed")

        return PipelineResult(
            total=len(results),
            working=working,
            failed=failed,
            persisted=persisted,
            stats=engine.stats.snapshot(__import__("time").perf_counter()),
        )
