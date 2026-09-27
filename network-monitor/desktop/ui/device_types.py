"""
Device type definitions for the topology canvas.

Milestone 3: five fixed types, each with a display label, node fill colour,
and a short text icon placeholder. Text-only so the repo stays asset-free.

The Enum itself will not change in later milestones; new types would be a
deliberate, additive change. The per-type metadata (colour, icon) may be
adjusted once we see the whole canvas filled with nodes, but no consumer of
this module should hard-code those values outside of it.
"""

from enum import Enum
from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class DeviceTypeStyle:
    """Visual style for a device type."""
    label: str          # Human-readable name, used in menus and tooltips.
    glyph: str          # Short text placeholder drawn in the node's corner.
    fill: QColor        # Node fill colour.


class DeviceType(Enum):
    """
    Initial supported device types.

    Values are short strings so they can be written to the DB verbatim at
    Milestone 8 without a translation table. Never compare against the raw
    string elsewhere; use the enum.
    """
    ROUTER  = "router"
    SWITCH  = "switch"
    SERVER  = "server"
    PC      = "pc"
    GENERIC = "generic"

    @property
    def style(self) -> DeviceTypeStyle:
        return _STYLES[self]

    @property
    def label(self) -> str:
        return self.style.label

    @property
    def glyph(self) -> str:
        return self.style.glyph

    @property
    def fill(self) -> QColor:
        return self.style.fill

    @classmethod
    def from_str(cls, value: str) -> "DeviceType":
        """
        Parse a stored value back to an enum member.

        Raises ValueError on unknown input. Callers that read from untrusted
        sources (the DB at Milestone 8) should catch and fall back to GENERIC.
        """
        return cls(value)


# Style table. Kept separate from the enum body so it's obviously editable
# without touching enum semantics.
#
# Colour choices: distinct enough to read at a glance when several nodes are
# on screen, muted enough that a full topology is not visually noisy. The
# generic type is intentionally the same blue as Milestone 2 so existing
# behaviour is unchanged for anyone creating a node without picking a type.
_STYLES = {
    DeviceType.ROUTER:  DeviceTypeStyle(
        label="Router",
        glyph="RT",
        fill=QColor("#ffcdd2"),   # muted red
    ),
    DeviceType.SWITCH:  DeviceTypeStyle(
        label="Switch",
        glyph="SW",
        fill=QColor("#c8e6c9"),   # muted green
    ),
    DeviceType.SERVER:  DeviceTypeStyle(
        label="Server",
        glyph="SRV",
        fill=QColor("#d1c4e9"),   # muted purple
    ),
    DeviceType.PC:      DeviceTypeStyle(
        label="PC",
        glyph="PC",
        fill=QColor("#fff9c4"),   # muted yellow
    ),
    DeviceType.GENERIC: DeviceTypeStyle(
        label="Generic device",
        glyph="DEV",
        fill=QColor("#e8f0fe"),   # same blue as Milestone 2 default
    ),
}