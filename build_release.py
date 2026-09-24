#!/usr/bin/env python3
"""Release build orchestrator for ProxyAtlas.

Steps:
    1. Clean previous builds.
    2. Validate dependencies.
    3. Regenerate branding assets.
    4. Run tests.
    5. Run linting.
    6. Build the PyInstaller executable (icons, themes, migrations, templates
       and assets are bundled via ProxyAtlas.spec).
    7. Create the release directory.

Usage:
    python build_release.py            # full pipeline
    python build_release.py --skip-tests --skip-lint
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
RELEASE = ROOT / "release"

REQUIRED_MODULES = [
    "PyQt6", "sqlalchemy", "alembic", "httpx", "aiohttp", "aiohttp_socks",
    "python_socks", "dns", "cryptography",
]


def _run(cmd: list[str], desc: str, check: bool = True) -> bool:
    print(f"\n=== {desc} ===")
    print("  $ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"  ! {desc} failed (exit {result.returncode})")
        if check:
            return False
    return True


def clean() -> None:
    print("\n=== Cleaning previous builds ===")
    for path in (DIST, BUILD, RELEASE):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            print(f"  removed {path.name}/")
    for spec_cache in ROOT.glob("*.spec.cache"):
        spec_cache.unlink(missing_ok=True)


def validate_dependencies() -> bool:
    print("\n=== Validating dependencies ===")
    import importlib

    missing = []
    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
            print(f"  ok  {mod}")
        except ImportError:
            print(f"  !!  {mod} MISSING")
            missing.append(mod)
    if missing:
        print(f"  Install missing modules: pip install {' '.join(missing)}")
        return False
    return True


def generate_assets() -> bool:
    script = ROOT / "assets" / "generate_assets.py"
    if not script.exists():
        return True
    return _run([sys.executable, str(script)], "Regenerating branding assets", check=False)


def run_tests() -> bool:
    return _run([sys.executable, "-m", "pytest", "-q"], "Running test suite")


def run_lint() -> bool:
    return _run([sys.executable, "-m", "ruff", "check", "app"], "Running linter")


def build_executable() -> bool:
    spec = ROOT / "ProxyAtlas.spec"
    return _run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec)], "Building executable")


def create_release() -> None:
    print("\n=== Creating release directory ===")
    RELEASE.mkdir(exist_ok=True)
    built = DIST / "ProxyAtlas"
    if built.exists():
        target = RELEASE / "ProxyAtlas"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(built, target)
        print(f"  release ready at {target}")
    else:
        print("  ! No built application found in dist/")
    for doc in ("README.md", "LICENSE", "CHANGELOG.md"):
        src = ROOT / doc
        if src.exists():
            shutil.copy2(src, RELEASE / doc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a ProxyAtlas release")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-lint", action="store_true")
    parser.add_argument("--skip-build", action="store_true", help="Run checks but do not run PyInstaller")
    args = parser.parse_args()

    clean()
    if not validate_dependencies():
        return 1
    generate_assets()

    if not args.skip_lint and not run_lint():
        print("\nLinting failed — aborting.")
        return 1
    if not args.skip_tests and not run_tests():
        print("\nTests failed — aborting.")
        return 1

    if args.skip_build:
        print("\nSkipping executable build (--skip-build).")
        return 0

    if not build_executable():
        print("\nExecutable build failed.")
        return 1
    create_release()
    print("\n=== Build complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
