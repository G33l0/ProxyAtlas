"""Tests for normalizer and deduplicator."""

from app.core.enums import Protocol
from app.discovery.normalizer import normalize_csv, normalize_json, normalize_lines
from app.proxy.deduplicator import count_duplicates, dedupe_candidates, dedupe_endpoints
from app.proxy.parser import parse_proxy


def test_normalize_lines():
    cands, errors = normalize_lines(["1.2.3.4:8080", "bad", "# c", "5.6.7.8:1080"], "src")
    assert len(cands) == 2
    assert len(errors) == 1


def test_normalize_csv():
    text = "host,port,protocol\n1.2.3.4,8080,http\n5.6.7.8,1080,socks5\n"
    cands, _ = normalize_csv(text, "csv")
    assert len(cands) == 2
    assert cands[1].endpoint.protocol == Protocol.SOCKS5


def test_normalize_json_objects():
    text = '[{"host": "1.2.3.4", "port": 8080, "protocol": "http"}, "5.6.7.8:1080"]'
    cands, _ = normalize_json(text, "json")
    assert len(cands) == 2


def test_dedupe_endpoints_prefers_credentials():
    eps = [parse_proxy("1.2.3.4:80"), parse_proxy("1.2.3.4:80:u:p")]
    out = dedupe_endpoints(eps)
    assert len(out) == 1
    assert out[0].has_credentials


def test_dedupe_candidates_merges_sources():
    from app.core.models import ProxyCandidate

    c1 = ProxyCandidate(parse_proxy("1.2.3.4:80"), source="a")
    c2 = ProxyCandidate(parse_proxy("1.2.3.4:80"), source="b")
    out = dedupe_candidates([c1, c2])
    assert len(out) == 1
    assert set(out[0].metadata["sources"]) == {"a", "b"}
    assert count_duplicates([c1, c2]) == 1
