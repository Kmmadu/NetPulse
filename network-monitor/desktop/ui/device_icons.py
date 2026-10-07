"""
SVG device-icon loader with an in-process pixmap cache.

Renders the icons shipped in desktop/assets/icons/ at arbitrary sizes
and tints. The SVG sources are monochrome black; tinting is applied at
render time by painting the SVG into a transparent pixmap and then
compositing the tint through SourceIn, so the SVG files themselves never
need to change when we tune colours.

Public API:
    icon_pixmap(device_type, tint, size)      -> QPixmap
    icon_pixmap_by_name(filename, tint, size) -> QPixmap

Both functions share the same rendering pipeline and cache. The
by-name variant exists for non-device icons — the header logo, and any
future UI element that wants to load an SVG from the assets directory
without tying the call to a DeviceType.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

from ui.device_types import DeviceType


# The assets directory is two levels up from this file:
#   desktop/ui/device_icons.py  ->  desktop/assets/icons/
ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

# Cache key: (filename, tint_rgba, size). Value: QPixmap.
#
# Keyed on the *filename* rather than a DeviceType so both public
# functions share one cache. A DeviceType resolves to its filename and
# then goes through the same path as a by-name call, so the same icon
# requested two different ways is rendered once.
_PIXMAP_CACHE: Dict[Tuple[str, int, int], QPixmap] = {}


def _render_tinted(filename: str, tint: QColor, size: int) -> QPixmap:
    """
    Shared rendering: load an SVG by filename from the assets directory,
    render at `size` x `size`, tint with `tint`, return a QPixmap.

    Defensive on missing or invalid files: returns a transparent pixmap
    of the requested size rather than raising. A broken icon degrades
    to "no icon" instead of crashing the caller.

    Not cached here; the two public functions cache their own results.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    path = ICON_DIR / filename
    if not path.exists():
        return pixmap

    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return pixmap

    # Step 1: render the SVG into the pixmap at full size.
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, pixmap.rect())

        # Step 2: tint. Painting the whole pixmap with the tint colour,
        # using SourceIn composition, replaces every opaque pixel's colour
        # with the tint and preserves alpha. Any pixel that was transparent
        # stays transparent.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), tint)
    finally:
        painter.end()

    return pixmap


def icon_pixmap(device_type: DeviceType, tint: QColor, size: int) -> QPixmap:
    """
    Return a QPixmap of the device type's icon, tinted with `tint`, at
    `size` x `size` pixels with a device pixel ratio of 1.

    The returned pixmap is cached: the same (type, tint, size) tuple
    returns the same object on repeated calls. Do not mutate the returned
    pixmap in place; treat it as immutable.

    If the SVG file is missing or unparseable, returns a transparent
    pixmap of the requested size. This keeps a broken icon from taking
    down the whole canvas; callers can rely on getting *something* back.
    """
    filename = device_type.icon_filename
    key = (filename, tint.rgba(), size)
    cached = _PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached

    pixmap = _render_tinted(filename, tint, size)
    _PIXMAP_CACHE[key] = pixmap
    return pixmap


def icon_pixmap_by_name(filename: str, tint: QColor, size: int) -> QPixmap:
    """
    Return a QPixmap of an arbitrary icon file, tinted with `tint`, at
    `size` x `size` pixels.

    Used for non-device icons — the header logo, and any future UI
    element that wants to load an SVG from the assets directory without
    a DeviceType. The filename is resolved under desktop/assets/icons/;
    a missing or invalid file returns a transparent pixmap rather than
    raising.

    Shares the same cache and rendering pipeline as icon_pixmap, so a
    file rendered through one path is reused by the other.
    """
    key = (filename, tint.rgba(), size)
    cached = _PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached

    pixmap = _render_tinted(filename, tint, size)
    _PIXMAP_CACHE[key] = pixmap
    return pixmap


def clear_cache() -> None:
    """
    Drop every cached pixmap. Not needed in normal operation; provided for
    tests and for the day we ship a theme switch.
    """
    _PIXMAP_CACHE.clear()