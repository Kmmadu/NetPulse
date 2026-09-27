"""
SVG device-icon loader with an in-process pixmap cache.

Renders the five type icons shipped in desktop/assets/icons/ at arbitrary
sizes and tints. The SVG sources are monochrome black; tinting is applied
at render time by painting the SVG into a transparent pixmap and then
compositing the tint through SourceIn, so the SVG files themselves never
need to change when we tune colours.

Public API:
    icon_pixmap(device_type, tint, size) -> QPixmap
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

from ui.device_types import DeviceType


# The assets directory is two levels up from this file:
#   desktop/ui/device_icons.py  ->  desktop/assets/icons/
ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

# Cache key: (device_type, tint_rgba, size). Value: QPixmap.
# The cache is module-level and unbounded in principle; in practice the
# number of distinct keys is tiny (5 types x ~4 statuses x 1-2 sizes).
_PIXMAP_CACHE: Dict[Tuple[DeviceType, int, int], QPixmap] = {}


def _icon_path(device_type: DeviceType) -> Path:
    return ICON_DIR / device_type.icon_filename


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
    key = (device_type, tint.rgba(), size)
    cached = _PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    path = _icon_path(device_type)
    if not path.exists():
        _PIXMAP_CACHE[key] = pixmap
        return pixmap

    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        _PIXMAP_CACHE[key] = pixmap
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

    _PIXMAP_CACHE[key] = pixmap
    return pixmap


def clear_cache() -> None:
    """
    Drop every cached pixmap. Not needed in normal operation; provided for
    tests and for the day we ship a theme switch.
    """
    _PIXMAP_CACHE.clear()