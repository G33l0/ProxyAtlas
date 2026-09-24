#!/usr/bin/env python3
"""Convenience launcher for ProxyAtlas.

With no arguments it launches the GUI; with CLI flags (e.g. ``--version``,
``--import``, ``--export``) it delegates to the command-line interface. This is
the PyInstaller entry point, so the packaged executable supports both modes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
