"""Tests for external-drive / custom database storage handling."""

import sqlite3
from pathlib import Path

from app.core.config import Settings
from app.core.paths import AppPaths
from app.services.storage import (
    normalize_db_path,
    relocate_database,
    resolve_storage,
    validate_db_location,
)


def test_default_location(tmp_path):
    ap = AppPaths(tmp_path / "data").ensure()
    s = Settings.load(tmp_path / "config.json")
    r = resolve_storage(s, ap)
    assert not r.is_custom
    assert r.path == ap.database_path


def test_custom_folder_gets_db_filename(tmp_path):
    ap = AppPaths(tmp_path / "data").ensure()
    s = Settings.load(tmp_path / "config.json")
    drive = tmp_path / "external"
    s.set("database", "path", str(drive))
    r = resolve_storage(s, ap)
    assert r.is_custom and not r.used_fallback
    assert r.path == drive / "proxyatlas.sqlite"


def test_custom_file_path(tmp_path):
    ap = AppPaths(tmp_path / "data").ensure()
    s = Settings.load(tmp_path / "config.json")
    target = tmp_path / "external" / "mydb.sqlite"
    s.set("database", "path", str(target))
    r = resolve_storage(s, ap)
    assert r.path == target
    assert r.url == f"sqlite:///{target}"


def test_unavailable_drive_falls_back(tmp_path):
    ap = AppPaths(tmp_path / "data").ensure()
    s = Settings.load(tmp_path / "config.json")
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    s.set("database", "path", str(blocker / "sub" / "db.sqlite"))
    r = resolve_storage(s, ap)
    assert r.used_fallback
    assert r.path == ap.database_path
    assert "unavailable" in r.message.lower()


def test_validate_and_normalize(tmp_path):
    ok, _ = validate_db_location(str(tmp_path / "drive"))
    assert ok
    assert normalize_db_path(str(tmp_path)).name == "proxyatlas.sqlite"
    assert normalize_db_path(str(tmp_path / "x.sqlite")).name == "x.sqlite"


def test_relocate_copies_db_and_updates_setting(tmp_path):
    ap = AppPaths(tmp_path / "data").ensure()
    s = Settings.load(tmp_path / "config.json")
    src = ap.database_path
    con = sqlite3.connect(src)
    con.execute("create table t(x)")
    con.commit()
    con.close()
    dest = tmp_path / "external" / "moved.sqlite"
    ok, _ = relocate_database(src, str(dest), s)
    assert ok
    assert dest.exists()
    assert Path(s.get("database", "path")) == dest
