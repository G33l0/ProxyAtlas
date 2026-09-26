"""Tests for the offline MMDB GeoIP provider (config / graceful degradation)."""

import pytest

from app.intelligence.manager import IntelligenceManager
from app.intelligence.providers.mmdb import MmdbProvider


async def test_unconfigured_returns_empty_and_valid():
    prov = MmdbProvider()
    prov.configure({})
    ok, msg = prov.validate_configuration()
    assert ok  # optional, so unconfigured is valid
    res = await prov.lookup("8.8.8.8")
    assert res.country is None and res.asn is None  # nothing without a DB


async def test_missing_database_file_reported_and_safe(tmp_path):
    prov = MmdbProvider()
    prov.configure({"city_db": str(tmp_path / "nope.mmdb")})
    ok, msg = prov.validate_configuration()
    assert not ok
    assert "not found" in msg.lower()
    # lookup still must not raise
    res = await prov.lookup("8.8.8.8")
    assert res.ip == "8.8.8.8"


async def test_private_ip_skipped():
    prov = MmdbProvider()
    prov.configure({})
    res = await prov.lookup("192.168.1.1")
    assert res.country is None


def test_manager_registers_mmdb_disabled_by_default():
    mgr = IntelligenceManager()
    mgr.register_defaults({})
    names = {s.name: s for s in mgr.status()}
    assert "mmdb" in names
    assert names["mmdb"].enabled is False  # off until a DB is configured


def test_manager_enables_mmdb_when_db_configured(tmp_path):
    db = tmp_path / "GeoLite2-City.mmdb"
    db.write_bytes(b"not-a-real-mmdb")  # presence is enough to auto-enable
    mgr = IntelligenceManager()
    mgr.register_defaults({"mmdb": {"city_db": str(db)}})
    names = {s.name: s for s in mgr.status()}
    assert names["mmdb"].enabled is True


@pytest.mark.asyncio
async def test_manager_lookup_survives_bad_mmdb(tmp_path):
    # A corrupt DB path must not break the manager's merged lookup.
    db = tmp_path / "bad.mmdb"
    db.write_bytes(b"garbage")
    mgr = IntelligenceManager()
    mgr.register_defaults({"mmdb": {"city_db": str(db), "enabled": True},
                           "ip-api": {"enabled": False}, "ipinfo": {"enabled": False}})
    res = await mgr.lookup("8.8.8.8")
    assert res.ip == "8.8.8.8"  # no crash despite the bad database
