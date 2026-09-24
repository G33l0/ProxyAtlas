"""Render ProxyAtlas branding assets from the source SVGs.

Produces PNG rasters at multiple sizes, a multi-resolution Windows ``.ico`` and
a macOS ``.icns``-compatible PNG set, plus the sidebar/about logos. Run with:

    python assets/generate_assets.py

Requires PyQt6 (uses the bundled Qt SVG renderer, no external tools).
"""

from __future__ import annotations

import os
import struct
import sys
import zlib
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtSvg import QSvgRenderer  # noqa: E402

_APP = None
ASSETS = Path(__file__).resolve().parent
LOGO_DIR = ASSETS / "logo"
ICON_DIR = ASSETS / "icons"


def render_svg(svg_path: Path, size: QSize) -> QImage:
    renderer = QSvgRenderer(QByteArray(svg_path.read_bytes()))
    image = QImage(size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
    painter.end()
    return image


def save_png(image: QImage, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path), "PNG")


def build_ico(png_sizes: dict[int, QImage], out_path: Path) -> None:
    """Assemble a multi-image .ico from rendered PNGs (pure Python)."""
    entries = []
    png_blobs = []
    for size in sorted(png_sizes):
        image = png_sizes[size]
        blob = _qimage_to_png_bytes(image)
        png_blobs.append(blob)
        entries.append(size)

    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=1 (icon), count
    directory = b""
    offset = 6 + count * 16
    for size, blob in zip(entries, png_blobs):
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset
        )
        offset += len(blob)
    with out_path.open("wb") as fh:
        fh.write(header)
        fh.write(directory)
        for blob in png_blobs:
            fh.write(blob)


def _qimage_to_png_bytes(image: QImage) -> bytes:
    from PyQt6.QtCore import QBuffer, QIODevice

    ba = QByteArray()
    buffer = QBuffer(ba)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(ba)


def main() -> int:
    # A QGuiApplication is required for text/font rendering in the SVGs.
    from PyQt6.QtGui import QGuiApplication

    global _APP
    if QGuiApplication.instance() is None:
        _APP = QGuiApplication(sys.argv[:1])

    mark = LOGO_DIR / "proxyatlas_mark.svg"
    logo = LOGO_DIR / "proxyatlas_logo.svg"
    if not mark.exists():
        print(f"Missing {mark}", file=sys.stderr)
        return 1

    ICON_DIR.mkdir(parents=True, exist_ok=True)

    # PNG rasters of the mark.
    sizes = [16, 24, 32, 48, 64, 128, 256, 512]
    rendered: dict[int, QImage] = {}
    for size in sizes:
        img = render_svg(mark, QSize(size, size))
        rendered[size] = img
        save_png(img, ICON_DIR / f"proxyatlas_{size}.png")

    # Primary app icon PNG + ICO.
    save_png(rendered[256], LOGO_DIR / "proxyatlas_icon.png")
    build_ico({s: rendered[s] for s in (16, 24, 32, 48, 64, 128, 256)}, LOGO_DIR / "proxyatlas.ico")

    # macOS icon (largest PNG; .icns fallback consumers accept PNG).
    save_png(rendered[512], LOGO_DIR / "proxyatlas.icns.png")

    # Sidebar + about-page logos (horizontal wordmark).
    if logo.exists():
        save_png(render_svg(logo, QSize(720, 200)), LOGO_DIR / "proxyatlas_logo.png")
        save_png(render_svg(logo, QSize(360, 100)), LOGO_DIR / "proxyatlas_sidebar.png")

    print(f"Generated assets in {ICON_DIR} and {LOGO_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# Silence unused import warnings for optional helpers.
_ = (zlib,)
