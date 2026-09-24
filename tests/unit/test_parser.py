"""Tests for the proxy parser."""

import pytest

from app.core.enums import Protocol
from app.core.exceptions import ParseError
from app.proxy.parser import parse_many, parse_proxy


@pytest.mark.parametrize(
    "raw,proto,host,port,creds",
    [
        ("1.2.3.4:8080", Protocol.HTTP, "1.2.3.4", 8080, False),
        ("1.2.3.4:8080:user:pass", Protocol.HTTP, "1.2.3.4", 8080, True),
        ("http://1.2.3.4:3128", Protocol.HTTP, "1.2.3.4", 3128, False),
        ("socks5://u:p@5.6.7.8:1080", Protocol.SOCKS5, "5.6.7.8", 1080, True),
        ("socks4://9.9.9.9:1080", Protocol.SOCKS4, "9.9.9.9", 1080, False),
        ("https://[2001:db8::1]:443", Protocol.HTTPS, "2001:db8::1", 443, False),
        ("proxy.example.com:3128", Protocol.HTTP, "proxy.example.com", 3128, False),
    ],
)
def test_parse_variants(raw, proto, host, port, creds):
    ep = parse_proxy(raw)
    assert ep.protocol == proto
    assert ep.host == host
    assert ep.port == port
    assert ep.has_credentials == creds


@pytest.mark.parametrize("bad", ["", "notaproxy", "1.2.3.4:99999", "1.2.3.4:0", "1.2.3.4", "http://", "999.999.999.999:80"])
def test_parse_rejects_malformed(bad):
    with pytest.raises(ParseError):
        parse_proxy(bad)


def test_parse_many_collects_errors_without_raising():
    endpoints, errors = parse_many(["1.2.3.4:80", "bad", "# comment", "", "5.6.7.8:99999"])
    assert len(endpoints) == 1
    assert len(errors) == 2


def test_url_roundtrip_credentials_hidden():
    ep = parse_proxy("http://user:secret@1.2.3.4:8080")
    assert "secret" not in ep.url(include_credentials=False)
    assert "secret" in ep.url(include_credentials=True)
