"""Regression tests for issues found in code review."""

from app.core.enums import Anonymity, DnsStatus, Protocol, ValidationStatus
from app.core.models import Endpoint, ProxyCandidate, ValidationResult
from app.database import repository as repo
from app.discovery.normalizer import _endpoint_from_dict, normalize_json
from app.testing.anonymity import analyze_anonymity


def test_json_credentials_with_special_chars_not_corrupted():
    ep = _endpoint_from_dict(
        {"host": "1.2.3.4", "port": 8080, "protocol": "http",
         "username": "a@b", "password": "p:q"},
        Protocol.HTTP,
    )
    assert ep.host == "1.2.3.4"
    assert ep.username == "a@b"
    assert ep.password == "p:q"


def test_normalize_json_objects_roundtrip():
    text = '[{"host":"9.9.9.9","port":1080,"protocol":"socks5","user":"u","pass":"x@y"}]'
    cands, errors = normalize_json(text, "j")
    assert not errors
    assert cands[0].endpoint.password == "x@y"


def test_anonymity_no_false_transparent_from_substring():
    # real_ip is a substring of an unrelated echoed value but not a real leak.
    anon, ev = analyze_anonymity({"x-forwarded-for": "11.2.3.44"}, exit_ip="5.6.7.8", real_ip="1.2.3.4")
    assert ev["real_ip_leaked"] is False
    assert anon != Anonymity.TRANSPARENT


def test_anonymity_detects_genuine_leak():
    anon, ev = analyze_anonymity({"x-forwarded-for": "1.2.3.4"}, exit_ip="5.6.7.8", real_ip="1.2.3.4")
    assert ev["real_ip_leaked"] is True
    assert anon == Anonymity.TRANSPARENT


def test_recheck_does_not_wipe_prior_anonymity_dns(ctx):
    with ctx.database.session() as s:
        ep = Endpoint("8.8.4.4", 3128, Protocol.HTTP)
        p = repo.upsert_proxy_from_candidate(s, ProxyCandidate(ep, source="t"), ctx.cipher)
        # Deep result establishes ELITE + DNS ok.
        deep = ValidationResult(ep, ValidationStatus.WORKING, exit_ip="8.8.4.4",
                                anonymity=Anonymity.ELITE, dns_status=DnsStatus.OK,
                                samples=1, successes=1)
        repo.apply_validation_result(s, p, deep, "deep")
        assert p.anonymity == "elite" and p.dns_status == "ok"
        # A lighter re-check with no signal must not downgrade.
        light = ValidationResult(ep, ValidationStatus.WORKING, exit_ip="8.8.4.4",
                                 anonymity=Anonymity.UNKNOWN, dns_status=DnsStatus.UNTESTED,
                                 samples=1, successes=1)
        repo.apply_validation_result(s, p, light, "quick")
        assert p.anonymity == "elite"
        assert p.dns_status == "ok"


async def test_internet_provider_breadth_matches_budget(ctx):
    prov = ctx.discovery.build(
        "internet", {"cidrs": "8.8.0.0/16", "ports": "80,443,1080", "max_candidates": 30}
    )
    cands = [c async for c in prov.discover()]
    distinct_hosts = {c.endpoint.host for c in cands}
    # 30 candidates / 3 ports -> ~10 distinct hosts, not 1.
    assert len(cands) == 30
    assert len(distinct_hosts) >= 9
