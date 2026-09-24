"""Tests for database repository, filters, settings and credentials."""

from app.core.config import DEFAULT_SETTINGS, Settings
from app.core.enums import Anonymity, Classification, Protocol, ValidationStatus
from app.core.models import (
    ClassificationResult,
    Endpoint,
    IntelligenceResult,
    ProxyCandidate,
    QualityScore,
    ValidationResult,
)
from app.database import repository as repo
from app.database.filters import FilterSpec


def _seed_working(ctx):
    with ctx.database.session() as s:
        cand = ProxyCandidate(Endpoint("8.8.8.8", 3128, Protocol.HTTP, "u", "p"), source="file")
        p = repo.upsert_proxy_from_candidate(s, cand, ctx.cipher)
        vr = ValidationResult(cand.endpoint, ValidationStatus.WORKING, latency_ms=120,
                              exit_ip="8.8.8.8", http_success=True, anonymity=Anonymity.ELITE,
                              samples=1, successes=1)
        repo.apply_validation_result(s, p, vr)
        repo.apply_intelligence(s, p, IntelligenceResult("8.8.8.8", country_code="US", isp="Google"))
        repo.apply_classification(s, p, ClassificationResult(Classification.DATACENTER, 0.9, ["ev"]))
        repo.apply_quality(s, p, QualityScore(88, {"connectivity": 100}))
        return p.id


def test_upsert_dedup(ctx):
    with ctx.database.session() as s:
        c = ProxyCandidate(Endpoint("1.1.1.1", 80, Protocol.HTTP), source="a")
        p1 = repo.upsert_proxy_from_candidate(s, c, ctx.cipher)
        s.flush()
        p2 = repo.upsert_proxy_from_candidate(s, ProxyCandidate(Endpoint("1.1.1.1", 80, Protocol.HTTP)), ctx.cipher)
        assert p1.id == p2.id


def test_credentials_encrypted_and_decrypt(ctx):
    pid = _seed_working(ctx)
    with ctx.database.session() as s:
        p = repo.get_proxy(s, pid)
        user, pw = repo.get_credentials(s, p, ctx.cipher)
        assert (user, pw) == ("u", "p")
        from app.database.models import ProxyCredential

        cred = s.get(ProxyCredential, p.credential_reference)
        assert cred.password_enc and cred.password_enc != "p"  # stored encrypted


def test_filter_query_and_count(ctx):
    _seed_working(ctx)
    with ctx.database.session() as s:
        spec = FilterSpec().add("status", "eq", "working").add("latency", "lt", 300)
        assert repo.count_proxies(s, spec) == 1
        rows = repo.query_proxies(s, spec)
        assert rows[0].classification == "datacenter"


def test_filter_spec_roundtrip():
    spec = FilterSpec().add("protocol", "eq", "socks5")
    spec.search = "abc"
    restored = FilterSpec.from_dict(spec.to_dict())
    assert restored.search == "abc"
    assert restored.conditions[0].field == "protocol"


def test_dashboard_stats(ctx):
    _seed_working(ctx)
    with ctx.database.session() as s:
        stats = repo.dashboard_stats(s)
        assert stats["total"] == 1 and stats["working"] == 1
        assert stats["datacenter"] == 1


def test_settings_persistence(tmp_path):
    cfg = tmp_path / "config.json"
    s = Settings.load(cfg)
    s.set("testing", "concurrency", 99)
    s.save()
    reloaded = Settings.load(cfg)
    assert reloaded.get("testing", "concurrency") == 99
    # Defaults still present.
    assert "appearance" in DEFAULT_SETTINGS


def test_collections_and_saved_filters(ctx):
    with ctx.database.session() as s:
        repo.save_collection(s, "US", FilterSpec().add("country_code", "eq", "US"))
        repo.save_filter(s, "fast", FilterSpec().add("latency", "lt", 200))
        assert any(c["name"] == "US" for c in repo.list_collections(s))
        assert any(f["name"] == "fast" for f in repo.list_saved_filters(s))
