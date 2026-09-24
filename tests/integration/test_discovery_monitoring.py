"""Integration tests: discovery engine and monitoring service."""

import json

import pytest

from app.core.enums import Protocol
from app.core.models import Endpoint, ProxyCandidate
from app.database import repository as repo
from app.services.monitoring import run_monitor_once
from app.services.pipeline import ProcessingPipeline
from app.testing.profiles import standard_profile


@pytest.mark.asyncio
async def test_discovery_file_provider(ctx, tmp_path):
    f = tmp_path / "list.txt"
    f.write_text("1.2.3.4:8080\nsocks5://5.6.7.8:1080\nbad\n1.2.3.4:8080\n")
    provider = ctx.discovery.build("file", {"path": str(f)})
    outcome = await ctx.discovery.run(provider)
    # 3 valid lines, 1 duplicate -> 2 unique.
    assert len(outcome.candidates) == 2


@pytest.mark.asyncio
async def test_discovery_internet_provider_bounded(ctx):
    provider = ctx.discovery.build("internet", {"cidrs": "8.8.8.0/28", "ports": "8080,1080", "max_candidates": 6})
    ok, _ = provider.validate_configuration()
    assert ok
    outcome = await ctx.discovery.run(provider, dedupe=False)
    assert len(outcome.candidates) == 6


@pytest.mark.asyncio
async def test_discovery_faulttolerant_bad_provider(ctx):
    provider = ctx.discovery.build("feed", {"url": "not-a-url"})
    outcome = await ctx.discovery.run(provider)
    assert outcome.errors  # captured, not raised
    assert outcome.candidates == []


@pytest.mark.asyncio
async def test_monitoring_records_result(ctx, mock_net):
    # Seed a working proxy via the pipeline first.
    settings = {
        "timeout": 5.0, "concurrency": 5,
        "validation_endpoints": [mock_net.ip_endpoint], "judge_endpoint": None,
    }
    pipeline = ProcessingPipeline(ctx.database, ctx.cipher, ctx.intelligence, settings, intelligence_enabled=False)
    await pipeline.process(
        [ProxyCandidate(Endpoint("127.0.0.1", mock_net.proxy_port, Protocol.HTTP), source="t")],
        standard_profile(timeout=5.0),
    )
    with ctx.database.session() as s:
        job = repo.upsert_monitoring_job(s, "all", "filter", json.dumps({"conditions": [], "combine": "and", "search": None}), 30)
        job_id = job.id
    # Point monitoring at the same mock endpoint.
    ctx.settings.update_section("testing", {"validation_endpoints": [mock_net.ip_endpoint], "timeout": 5.0})
    outcome = await run_monitor_once(ctx, job_id, "filter", json.dumps({"conditions": [], "combine": "and", "search": None}))
    assert outcome.total >= 1
    with ctx.database.session() as s:
        history = repo.monitoring_history(s, job_id)
        assert history and history[-1].total >= 1
