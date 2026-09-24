"""Integration tests: validation engine and full processing pipeline."""

import pytest

from app.core.enums import Protocol, ValidationStatus
from app.core.models import Endpoint, ProxyCandidate
from app.database import repository as repo
from app.database.filters import FilterSpec
from app.services.pipeline import ProcessingPipeline
from app.testing.engine import JobControl, ValidationEngine
from app.testing.profiles import quick_profile, standard_profile
from app.testing.validator import validate_proxy


@pytest.mark.asyncio
async def test_validate_working_and_failed(mock_net):
    good = Endpoint("127.0.0.1", mock_net.proxy_port, Protocol.HTTP)
    bad = Endpoint("127.0.0.1", 59999, Protocol.HTTP)
    prof = standard_profile(timeout=5.0)
    ok = await validate_proxy(good, prof, [mock_net.ip_endpoint], mock_net.judge_endpoint)
    fail = await validate_proxy(bad, prof, [mock_net.ip_endpoint], mock_net.judge_endpoint)
    assert ok.status == ValidationStatus.WORKING
    assert ok.exit_ip == "203.0.113.77"
    assert ok.latency_ms is not None
    assert fail.status in (ValidationStatus.FAILED, ValidationStatus.TIMEOUT)


@pytest.mark.asyncio
async def test_never_working_without_proxied_request():
    # A plain TCP server that accepts connections but is NOT a proxy (returns a
    # fixed non-IP HTML page) must never be classified WORKING, even though its
    # port responds to TCP.
    import socketserver
    import threading

    class _Dumb(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                self.request.recv(1024)
                self.request.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\nhello, world!"
                )
            except OSError:
                pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Dumb)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    endpoint = Endpoint("127.0.0.1", port, Protocol.HTTP)
    res = await validate_proxy(endpoint, quick_profile(timeout=5.0), ["http://example.invalid/ip"])
    assert res.status != ValidationStatus.WORKING
    server.shutdown()


@pytest.mark.asyncio
async def test_engine_concurrency_and_stats(mock_net):
    good = Endpoint("127.0.0.1", mock_net.proxy_port, Protocol.HTTP)
    engine = ValidationEngine(quick_profile(timeout=5.0), [mock_net.ip_endpoint], None, concurrency=5)
    results = await engine.run([good, good, good])
    assert len(results) == 3
    assert engine.stats.working == 3
    assert engine.stats.success_rate == 100.0


@pytest.mark.asyncio
async def test_stop_control(mock_net):
    control = JobControl()
    control.stop()
    engine = ValidationEngine(quick_profile(timeout=5.0), [mock_net.ip_endpoint], None, control=control)
    good = Endpoint("127.0.0.1", mock_net.proxy_port, Protocol.HTTP)
    results = await engine.run([good, good])
    # Stopped before running -> nothing completed.
    assert engine.stats.completed == 0
    assert results == []


@pytest.mark.asyncio
async def test_full_pipeline_persists(ctx, mock_net):
    settings = {
        "timeout": 5.0, "concurrency": 5,
        "validation_endpoints": [mock_net.ip_endpoint],
        "judge_endpoint": mock_net.judge_endpoint,
    }
    pipeline = ProcessingPipeline(ctx.database, ctx.cipher, ctx.intelligence, settings, intelligence_enabled=False)
    cands = [
        ProxyCandidate(Endpoint("127.0.0.1", mock_net.proxy_port, Protocol.HTTP), source="t"),
        ProxyCandidate(Endpoint("127.0.0.1", 59998, Protocol.HTTP), source="t"),
    ]
    result = await pipeline.process(cands, standard_profile(timeout=5.0))
    assert result.working == 1
    assert result.failed == 1
    with ctx.database.session() as s:
        working = repo.query_proxies(s, FilterSpec().add("status", "eq", "working"))
        assert len(working) == 1
        assert working[0].exit_ip == "203.0.113.77"
        assert working[0].score > 0
