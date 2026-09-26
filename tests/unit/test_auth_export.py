"""Tests for optional authenticated (credential-inclusive) export."""

from app.core.enums import Protocol
from app.core.models import Endpoint, ProxyCandidate
from app.database import repository as repo
from app.services.exporters import export_rows, proxy_to_row


def _seed_with_creds(ctx):
    with ctx.database.session() as s:
        ep = Endpoint("1.2.3.4", 8080, Protocol.HTTP, "user", "p@ss:1")
        p = repo.upsert_proxy_from_candidate(s, ProxyCandidate(ep, source="t"), ctx.cipher)
        s.flush()
        return p.id


def test_default_export_omits_credentials(ctx, tmp_path):
    _seed_with_creds(ctx)
    with ctx.database.session() as s:
        rows = [proxy_to_row(p) for p in repo.query_proxies(s)]
    assert "username" not in rows[0]
    out = tmp_path / "o.txt"
    export_rows(rows, out, "txt", txt_format="protocol_url", working_only=False)
    assert "user" not in out.read_text()


def test_opt_in_export_includes_credentials(ctx, tmp_path):
    _seed_with_creds(ctx)
    with ctx.database.session() as s:
        rows = [proxy_to_row(p, ctx.cipher, True) for p in repo.query_proxies(s)]
    assert rows[0]["username"] == "user"
    assert rows[0]["password"] == "p@ss:1"

    # TXT protocol_url embeds credentials.
    txt = tmp_path / "c.txt"
    export_rows(rows, txt, "txt", txt_format="protocol_url", working_only=False)
    assert txt.read_text().strip() == "http://user:p@ss:1@1.2.3.4:8080"

    # CSV gains credential columns.
    csvp = tmp_path / "c.csv"
    export_rows(rows, csvp, "csv", working_only=False)
    header = csvp.read_text().splitlines()[0]
    assert "username" in header and "password" in header

    # JSON carries the fields.
    import json

    jsonp = tmp_path / "c.json"
    export_rows(rows, jsonp, "json", working_only=False)
    data = json.loads(jsonp.read_text())
    assert data["proxies"][0]["username"] == "user"
