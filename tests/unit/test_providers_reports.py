"""Tests for providers, exporters and report generation."""

import json

import pytest

from app.core.enums import ValidationStatus
from app.intelligence.geoip import is_private_or_reserved
from app.intelligence.manager import IntelligenceManager
from app.intelligence.providers.builtin import BuiltinIntelligenceProvider
from app.reports.generator import build_report_html
from app.services.exporters import EXPORT_COLUMNS, export_rows

SAMPLE_ROWS = [
    {c: None for c in EXPORT_COLUMNS} | {
        "host": "1.2.3.4", "port": 8080, "protocol": "http",
        "status": ValidationStatus.WORKING.value, "exit_ip": "5.6.7.8",
        "country": "United States", "classification": "datacenter",
        "latency": 120, "reliability": 95, "score": 88,
    },
    {c: None for c in EXPORT_COLUMNS} | {
        "host": "9.9.9.9", "port": 3128, "protocol": "http",
        "status": ValidationStatus.FAILED.value,
    },
]


def test_export_txt_working_only(tmp_path):
    path = tmp_path / "out.txt"
    count = export_rows(SAMPLE_ROWS, path, "txt", working_only=True)
    assert count == 1
    assert path.read_text().strip() == "1.2.3.4:8080"


def test_export_txt_protocol_format(tmp_path):
    path = tmp_path / "o.txt"
    export_rows(SAMPLE_ROWS, path, "txt", working_only=True, txt_format="protocol_url")
    assert path.read_text().strip() == "http://1.2.3.4:8080"


def test_export_csv_json(tmp_path):
    assert export_rows(SAMPLE_ROWS, tmp_path / "o.csv", "csv") == 2
    assert export_rows(SAMPLE_ROWS, tmp_path / "o.json", "json") == 2
    data = json.loads((tmp_path / "o.json").read_text())
    assert data["count"] == 2


def test_report_html_escapes_and_summarizes():
    rows = SAMPLE_ROWS + [{c: None for c in EXPORT_COLUMNS} | {
        "host": "<script>", "port": 1, "protocol": "http", "status": "working",
        "exit_ip": "1.1.1.1", "classification": "residential", "latency": 50, "score": 70,
    }]
    html = build_report_html(rows, "Test")
    assert "&lt;script&gt;" in html  # escaped
    assert "<script>" not in html.split("<style>")[1]  # no raw injection in body
    assert "Total Proxies" in html


def test_export_unsupported_format(tmp_path):
    with pytest.raises(ValueError):
        export_rows(SAMPLE_ROWS, tmp_path / "o.xyz", "xyz")


def test_private_range_detection():
    assert is_private_or_reserved("192.168.1.1")
    assert is_private_or_reserved("127.0.0.1")
    assert not is_private_or_reserved("8.8.8.8")


@pytest.mark.asyncio
async def test_builtin_provider_skips_private():
    mgr = IntelligenceManager()
    mgr.register(BuiltinIntelligenceProvider())
    res = await mgr.lookup("192.168.0.1")
    assert res.country is None  # skipped, no lookup


@pytest.mark.asyncio
async def test_manager_merges_and_isolates_failures():
    class Boom(BuiltinIntelligenceProvider):
        def name(self):
            return "boom"

        async def lookup(self, ip):
            raise RuntimeError("provider down")

    mgr = IntelligenceManager()
    mgr.register(Boom())
    # Should not raise despite provider failure.
    res = await mgr.lookup("8.8.8.8")
    assert res.ip == "8.8.8.8"
    statuses = {s.name: s for s in mgr.status()}
    assert statuses["boom"].last_error
