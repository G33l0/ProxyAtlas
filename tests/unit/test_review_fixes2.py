"""Regression tests for the second code-review round."""


from app.core.enums import Protocol, ValidationStatus
from app.core.models import Endpoint, ProxyCandidate, ValidationResult
from app.database import repository as repo
from app.database.filters import FilterSpec
from app.services.exporters import export_rows


def test_delete_other_protocol_at_hostport(ctx):
    with ctx.database.session() as s:
        # A stale mislabeled http row exists.
        repo.upsert_proxy_from_candidate(
            s, ProxyCandidate(Endpoint("1.2.3.4", 1080, Protocol.HTTP), source="x"), ctx.cipher
        )
        s.flush()
        removed = repo.delete_proxies_at_hostport_except(s, "1.2.3.4", 1080, "socks5")
        assert removed == 1
        assert repo.count_proxies(s) == 0


async def test_autodetect_replaces_not_duplicates(ctx, monkeypatch):
    """A protocol-corrected result must leave exactly one row (the corrected one)."""
    import app.testing.engine as engine_mod

    # Pre-seed a stale mislabeled http row (e.g. from an earlier failed run).
    with ctx.database.session() as s:
        repo.upsert_proxy_from_candidate(
            s, ProxyCandidate(Endpoint("9.9.9.9", 1080, Protocol.HTTP), source="feed"), ctx.cipher
        )

    # Engine returns a corrected SOCKS5 WORKING result for the http candidate.
    async def fake_run(self, endpoints, on_result=None, on_progress=None):
        out = []
        for ep in endpoints:
            corrected = Endpoint(ep.host, ep.port, Protocol.SOCKS5, ep.username, ep.password)
            out.append(ValidationResult(corrected, ValidationStatus.WORKING, exit_ip="5.5.5.5",
                                        latency_ms=100, samples=1, successes=1))
        return out

    monkeypatch.setattr(engine_mod.ValidationEngine, "run", fake_run)

    from app.services.pipeline import ProcessingPipeline
    from app.testing.profiles import quick_profile

    pipe = ProcessingPipeline(ctx.database, ctx.cipher, ctx.intelligence,
                              {"validation_endpoints": ["u"], "concurrency": 2}, intelligence_enabled=False)
    cand = ProxyCandidate(Endpoint("9.9.9.9", 1080, Protocol.HTTP), source="feed")
    await pipe.process([cand], quick_profile())

    with ctx.database.session() as s:
        rows = repo.query_proxies(s, FilterSpec())
        assert len(rows) == 1  # replaced, not duplicated
        assert rows[0].protocol == "socks5"
        assert rows[0].status == "working"


async def test_monitor_reschedules_on_failure(ctx, monkeypatch):
    """A monitor whose validation raises still records a result (advances schedule)."""
    import app.services.monitoring as mon

    with ctx.database.session() as s:
        # One proxy so candidates is non-empty and the pipeline path runs.
        repo.upsert_proxy_from_candidate(
            s, ProxyCandidate(Endpoint("1.1.1.1", 80, Protocol.HTTP), source="x"), ctx.cipher
        )
        job = repo.upsert_monitoring_job(s, "m", "filter",
                                         '{"conditions": [], "combine": "and", "search": null}', 30)
        job_id = job.id

    async def boom(self, *a, **k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(mon.ProcessingPipeline, "process", boom)
    outcome = await mon.run_monitor_once(ctx, job_id, "filter",
                                         '{"conditions": [], "combine": "and", "search": null}')
    assert outcome.working == 0
    with ctx.database.session() as s:
        history = repo.monitoring_history(s, job_id)
        assert len(history) == 1  # a result was recorded despite the failure
        job = next(j for j in repo.list_monitoring_jobs(s) if j.id == job_id)
        assert job.next_run_at is not None  # schedule advanced


def test_csv_credentials_with_empty_username(tmp_path):
    rows = [{"host": "1.2.3.4", "port": 8080, "protocol": "http", "status": "working",
             "username": None, "password": "secret"}]
    out = tmp_path / "c.csv"
    export_rows(rows, out, "csv", working_only=False)
    header = out.read_text().splitlines()[0]
    assert "password" in header  # password not dropped despite empty username


def test_html_export_includes_credentials_when_present(tmp_path):
    rows = [{"host": "1.2.3.4", "port": 8080, "protocol": "http", "status": "working",
             "username": "u", "password": "p"}]
    out = tmp_path / "c.html"
    export_rows(rows, out, "html", working_only=False)
    body = out.read_text()
    assert "username" in body and "password" in body
