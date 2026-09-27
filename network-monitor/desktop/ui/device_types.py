"""
Device type definitions for the topology canvas.

Each type has a display label, a short text glyph (used in menus and
tooltips), and the filename of its SVG icon under desktop/assets/icons/.

The SVG itself is monochrome; tinting and size are applied at render time
by ui/device_icons.py.
"""

from enum import Enum
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceTypeStyle:
    """Metadata for a device type. Icon colour is not stored here; the
    icon is tinted at paint time according to context."""
    label: str
    glyph: str
    icon_filename: str


class DeviceType(Enum):
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
    def icon_filename(self) -> str:
        return self.style.icon_filename

    @classmethod
    def from_str(cls, value: str) -> "DeviceType":
        """
        Parse a stored value back to an enum member.

        Raises ValueError on unknown input. Callers that read from untrusted
        sources (the DB at Milestone 8) should catch and fall back to GENERIC.
        """
        return cls(value)


_STYLES = {
    DeviceType.ROUTER:  DeviceTypeStyle(
        label="Router",
        glyph="RT",
        icon_filename="router.svg",
    ),
    DeviceType.SWITCH:  DeviceTypeStyle(
        label="Switch",
        glyph="SW",
        icon_filename="switch.svg",
    ),
    DeviceType.SERVER:  DeviceTypeStyle(
        label="Server",
        glyph="SRV",
        icon_filename="server.svg",
    ),
    DeviceType.PC:      DeviceTypeStyle(
        label="PC",
        glyph="PC",
        icon_filename="pc.svg",
    ),
    DeviceType.GENERIC: DeviceTypeStyle(
        label="Generic device",
        glyph="DEV",
        icon_filename="generic.svg",
    ),
}