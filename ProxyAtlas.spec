# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ProxyAtlas.

Bundles the application together with assets (logo/icons), Alembic migrations
and report templates into a single windowed executable. Build with:

    pyinstaller ProxyAtlas.spec
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH)

datas = [
    (str(project_root / "assets"), "assets"),
    (str(project_root / "app" / "database" / "migrations"), "app/database/migrations"),
    (str(project_root / "app" / "reports" / "templates"), "app/reports/templates"),
    (str(project_root / "alembic.ini"), "."),
]

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("aiohttp_socks")
    + collect_submodules("python_socks")
    + ["httpx", "httpcore", "socksio", "dns", "cryptography", "alembic"]
)

icon_path = project_root / "assets" / "logo" / "proxyatlas.ico"

block_cipher = None

a = Analysis(
    [str(project_root / "run.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6", "PyQt5"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProxyAtlas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ProxyAtlas",
)
