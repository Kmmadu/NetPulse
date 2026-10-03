"""
Device node — the visual representation of a single device on the canvas.

Milestone 6: stores the last observed latency, reflects status and latency
in an auto-updating tooltip, and calls _update_tooltip() from every setter
that changes displayed data.

Milestone 6 (revision): the type icon is now tinted with the status colour,
so a green ring frames a green icon, a red ring frames a red icon, and so
on. The ring remains grey for UNKNOWN, matching the icon.
"""

import uuid

from PySide6.QtCore import QRectF, QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QPen, QColor, QFont
from PySide6.QtWidgets import (
    QGraphicsObject,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
)

from ui.device_types import DeviceType
from ui.device_icons import icon_pixmap


class DeviceNode(QGraphicsObject):
    """A movable, selectable, deletable device node."""

    # Emitted whenever the node's position changes in scene coordinates.
    # ConnectionItem subscribes to this so that edges follow the node during
    # drags. Emitted from itemChange().
    positionChanged = Signal(QPointF)

    # Emitted when the user double-clicks the node. The canvas connects to
    # this and opens the edit dialog. Emitting rather than opening the
    # dialog directly keeps DeviceNode free of any knowledge of dialogs.
    doubleClicked = Signal(object)   # argument: this DeviceNode

    WIDTH = 120
    HEIGHT = 60
    CORNER_RADIUS = 8

    # ------------------------------------------------------------------
    # Visual constants
    # ------------------------------------------------------------------

    # Neutral fill, same for every device type. The fill deliberately does
    # not carry any meaning; status is conveyed by the ring and the icon.
    FILL_COLOR = QColor("#f4f5f7")

    # Border. Selection is shown by weight and colour of the border, not by
    # any change to fill, ring, or icon, so it cannot be confused with status.
    BORDER_COLOR = QColor("#1a73e8")
    BORDER_COLOR_SELECTED = QColor("#0b47a1")
    BORDER_WIDTH = 1.5
    BORDER_WIDTH_SELECTED = 2.5

    # Name text.
    TEXT_COLOR = QColor("#202124")

    # Status colours. Used for both the ring stroke and the icon tint, so
    # the ring-and-icon area reads as a single status colour at a glance.
    # The four keys match app/models/device.py's DeviceStatus enum values.
    RING_COLOR_UP        = QColor("#34a853")   # green
    RING_COLOR_DEGRADED  = QColor("#fbbc04")   # yellow
    RING_COLOR_DOWN      = QColor("#ea4335")   # red
    RING_COLOR_UNKNOWN   = QColor("#9aa0a6")   # grey

    # Ring geometry.
    RING_DIAMETER = 36
    RING_STROKE = 4
    ICON_SIZE = 20

    # Alpha for the icon tint. 165 keeps the icon legible as a shape while
    # still reading as "this colour" at a glance.
    ICON_TINT_ALPHA = 165

    # Alpha for the fill inside the ring. Very low, so the ring stroke still
    # dominates; but enough that the interior of the ring reads as the same
    # colour family as the ring.
    RING_FILL_ALPHA = 38

    def __init__(
        self,
        name: str = "device",
        ip_address: str = "",
        position: QPointF = None,
        device_type: DeviceType = DeviceType.GENERIC,
        monitoring_enabled: bool = True,
        status: str = "UNKNOWN",
    ):
        super().__init__()

        self.device_id: str = str(uuid.uuid4())
        self.name: str = name
        self.ip_address: str = ip_address
        self.device_type: DeviceType = device_type
        self.monitoring_enabled: bool = monitoring_enabled

        # Status string, mirroring DeviceStatus values as plain strings so
        # the desktop app does not need to translate between enum and
        # display. The worker feeds "UP" / "DEGRADED" / "DOWN" / "UNKNOWN".
        self.status: str = status

        # Last observed latency in milliseconds, or None if the last check
        # did not produce a latency (device DOWN, or no cycle completed yet).
        # Displayed only in the tooltip; not part of the node's visual.
        self._last_latency_ms: float | None = None

        self._rect = QRectF(0, 0, self.WIDTH, self.HEIGHT)

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setZValue(0)

        # Populate the tooltip before any status update arrives, so it is
        # correct on the very first hover.
        self._update_tooltip()

        if position is not None:
            self.setPos(position)

    # ------------------------------------------------------------------
    # QGraphicsItem required overrides
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        pad = 1.0
        return self._rect.adjusted(-pad, -pad, pad, pad)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)

        # 1. Node body: neutral fill, uniform rounded rect.
        painter.setBrush(QBrush(self.FILL_COLOR))
        if self.isSelected():
            border = QPen(self.BORDER_COLOR_SELECTED, self.BORDER_WIDTH_SELECTED)
        else:
            border = QPen(self.BORDER_COLOR, self.BORDER_WIDTH)
        if not self.monitoring_enabled:
            # Dashed border is the visual cue for a node whose monitoring is
            # off; everything else about the node is unchanged.
            border.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(border)
        painter.drawRoundedRect(
            self._rect, self.CORNER_RADIUS, self.CORNER_RADIUS
        )

        # 2. Status colour, shared by the ring stroke, the ring interior
        # fill, and the icon tint so the whole indicator reads as one colour.
        status_color = self._ring_color_for_status()

        ring_cx = self.WIDTH / 2
        ring_cy = 22.0
        ring_radius = self.RING_DIAMETER / 2

        # 2a. Ring interior fill: a very faint tint of the same colour.
        fill = QColor(status_color)
        fill.setAlpha(self.RING_FILL_ALPHA)
        painter.setBrush(QBrush(fill))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(ring_cx, ring_cy), ring_radius, ring_radius)

        # 2b. Ring stroke: full-opacity, thickened.
        ring_pen = QPen(status_color, self.RING_STROKE)
        ring_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(ring_cx, ring_cy), ring_radius, ring_radius)

        # 3. Type icon, tinted with the status colour.
        icon_tint = QColor(status_color)
        icon_tint.setAlpha(self.ICON_TINT_ALPHA)
        pm = icon_pixmap(self.device_type, icon_tint, self.ICON_SIZE)
        icon_x = int(ring_cx - self.ICON_SIZE / 2)
        icon_y = int(ring_cy - self.ICON_SIZE / 2)
        painter.drawPixmap(icon_x, icon_y, pm)

        # 4. Name, centred horizontally, in the lower portion of the node.
        name_font = QFont()
        name_font.setPointSize(10)
        painter.setFont(name_font)
        painter.setPen(QPen(self.TEXT_COLOR))

        name_rect = QRectF(
            4,
            ring_cy + ring_radius + 1,
            self.WIDTH - 8,
            self.HEIGHT - (ring_cy + ring_radius + 1) - 4,
        )
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self.name,
        )

    def _ring_color_for_status(self) -> QColor:
        """Map the status string to a colour. Unknown statuses are treated
        as UNKNOWN (grey). Used for both the ring and the icon tint."""
        table = {
            "UP": self.RING_COLOR_UP,
            "DEGRADED": self.RING_COLOR_DEGRADED,
            "DOWN": self.RING_COLOR_DOWN,
            "UNKNOWN": self.RING_COLOR_UNKNOWN,
        }
        return table.get(self.status, self.RING_COLOR_UNKNOWN)

    # ------------------------------------------------------------------
    # QGraphicsItem hooks
    # ------------------------------------------------------------------

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()

        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.positionChanged.emit(self.scene_centre())

        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        # Emit and accept. Do not call super(): the base implementation would
        # begin a drag, and we do not want a double-click to also move the
        # node. The canvas is responsible for opening the dialog.
        self.doubleClicked.emit(self)
        event.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_device_type(self, device_type: DeviceType) -> None:
        if device_type == self.device_type:
            return
        self.device_type = device_type
        self._invalidate_cache()
        self._update_tooltip()

    def set_status(self, status: str) -> None:
        """
        Set the status string. Called by the canvas from the worker's
        cycleComplete slot. Idempotent: no-op if the status is unchanged,
        so repeated cycles reporting the same status do not thrash the
        pixmap cache.
        """
        if status == self.status:
            return
        self.status = status
        self._invalidate_cache()
        self._update_tooltip()

    def set_latency(self, latency_ms) -> None:
        """
        Store the latest observed latency for the tooltip. Accepts None for
        devices whose last check produced no latency (DOWN, or no cycle yet).

        Does not invalidate the pixmap cache: latency is not drawn on the
        node, only shown in the tooltip.
        """
        self._last_latency_ms = latency_ms
        self._update_tooltip()

    def set_monitoring_enabled(self, enabled: bool) -> None:
        if enabled == self.monitoring_enabled:
            return
        self.monitoring_enabled = enabled
        self._invalidate_cache()
        self._update_tooltip()

    def _invalidate_cache(self) -> None:
        """Force a re-render of the cached pixmap. Any method that changes a
        visual attribute must call this; DeviceCoordinateCache otherwise
        keeps the stale painting on screen."""
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

    def _update_tooltip(self) -> None:
        """
        Rebuild the tooltip from current state. Cheap (string formatting
        only); called from every setter and from __init__.
        """
        latency = (
            f"{self._last_latency_ms:.1f} ms"
            if self._last_latency_ms is not None
            else "—"
        )
        monitoring = "on" if self.monitoring_enabled else "off"
        self.setToolTip(
            f"{self.name}\n"
            f"IP: {self.ip_address or '(unset)'}\n"
            f"Type: {self.device_type.label}\n"
            f"Status: {self.status}\n"
            f"Latency: {latency}\n"
            f"Monitoring: {monitoring}"
        )

    def centre(self) -> QPointF:
        return self._rect.center()

    def scene_centre(self) -> QPointF:
        return self.mapToScene(self._rect.center())

    def connection_anchor(self) -> QPointF:
        """Kept for symmetry with rect_in_scene(). ConnectionItem currently
        uses rect_in_scene() and scene_centre() directly."""
        return self.scene_centre()

    def rect_in_scene(self) -> QRectF:
        """
        The node's bounding rectangle, in scene coordinates.

        Used by ConnectionItem to clip edge endpoints to the node's border
        so that only the segment of the edge that lies in the visible gap
        between two nodes is drawn and clickable.
        """
        top_left = self.mapToScene(self._rect.topLeft())
        bottom_right = self.mapToScene(self._rect.bottomRight())
        return QRectF(top_left, bottom_right)