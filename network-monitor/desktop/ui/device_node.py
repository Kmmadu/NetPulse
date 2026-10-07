"""
Device node — the visual representation of a single device on the canvas.

Milestone 6: stores the last observed latency, reflects status and latency
in an auto-updating tooltip, and calls _update_tooltip() from every setter
that changes displayed data.

Milestone 6 (revision): the type icon is tinted with the status colour.

Milestone 7.75: the ring-and-icon colour is the maximum of two signals —
the device status (UP / DEGRADED / DOWN / UNKNOWN) and the engine's
suboptimality severity (none / mild / moderate / severe / critical). A
device that is technically reachable but whose link quality is degraded
shows an amber or red ring-and-icon, not green. The severity is reflected
in the ring itself; the tooltip shows the reason.

Milestone 7.98: node cards are now dark slate instead of pale grey, and
the name is drawn in bold near-white (contrast ratio ~14:1 against the
card). The IP is not shown on the card — it remains available in the
tooltip. The ring, icon, status palette, and composite-severity logic
are unchanged.

Milestone 7.99: adds a statusChanged signal, emitted from set_status().
ConnectionItem subscribes to this so that edges can repaint when their
endpoints transition between UP / DEGRADED / DOWN / UNKNOWN. The signal
is additive — nothing else in the class changes.

Milestone 7.102: adds find-highlight state. Two new methods,
set_find_highlight(current: bool) and clear_find_highlight(), and one
additional branch in paint() that selects the border colour when the
node is a search match. Selection overrides highlight — a selected
node always shows the selection border, regardless of find state.
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

    # Emitted whenever the node's status changes (UP / DEGRADED / DOWN /
    # UNKNOWN). ConnectionItem subscribes to this so that edges can
    # reflect the status of their endpoints — specifically, an edge
    # touching a DOWN or DEGRADED node is visually muted. Emitted from
    # set_status(); see that method.
    statusChanged = Signal(str)

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

    # Card fill. Dark slate, sitting between the canvas background
    # (#0F1117) and the node's border. The value is deliberately the same
    # as the grid base colour (#1A1D24) so a node reads as "raised from
    # the grid" rather than as a distinct material. The fill carries no
    # status meaning; status is conveyed by the ring and the icon.
    FILL_COLOR = QColor(26, 29, 36)           # #1A1D24, dark slate

    # Border. Selection is shown by weight and colour of the border, not by
    # any change to fill, ring, or icon, so it cannot be confused with
    # status or quality.
    BORDER_COLOR = QColor("#1a73e8")
    BORDER_COLOR_SELECTED = QColor("#0b47a1")
    BORDER_WIDTH = 1.5
    BORDER_WIDTH_SELECTED = 2.5

    # Find-highlight border colours. The "match" border is a soft
    # yellow; the "current" border is a brighter amber so the current
    # match is distinguishable from its peers at a glance. Both are
    # distinct from the selection border (dark blue) so a node can be
    # both selected and highlighted without ambiguity — selection wins
    # in that case, since the user's explicit interaction should take
    # precedence over a passive search result.
    FIND_MATCH_COLOR = QColor("#F5C542")
    FIND_CURRENT_COLOR = QColor("#FF8B3D")
    FIND_BORDER_WIDTH = 2.5

    # Text colour. Chosen for contrast against FILL_COLOR:
    #   NAME_COLOR #E8EAED has a contrast ratio of ~14:1 (WCAG AAA).
    NAME_COLOR = QColor("#E8EAED")

    # Colours used by the effective-ring computation. The status colours
    # (green / amber / red / grey) are the same ones used since Milestone 6.
    # One additional colour is used for the worst suboptimal severity.
    RING_COLOR_UP        = QColor("#34a853")   # green
    RING_COLOR_DEGRADED  = QColor("#fbbc04")   # amber
    RING_COLOR_DOWN      = QColor("#ea4335")   # red
    RING_COLOR_UNKNOWN   = QColor("#9aa0a6")   # grey
    RING_COLOR_CRITICAL  = QColor("#a50e0e")   # dark red, for severity=critical

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

        # Status string, mirroring DeviceStatus values as plain strings.
        # The worker feeds "UP" / "DEGRADED" / "DOWN" / "UNKNOWN".
        self.status: str = status

        # Last observed latency in milliseconds, or None if the last check
        # did not produce a latency (device DOWN, or no cycle completed yet).
        # Displayed only in the tooltip; not part of the node's visual.
        self._last_latency_ms: float | None = None

        # Suboptimal state. Populated by set_suboptimal() from the cycle
        # result. Severity is one of "none", "mild", "moderate", "severe",
        # "critical". Reasons is a list of short strings from the engine.
        self._suboptimal_severity: str = "none"
        self._suboptimal_reasons: list[str] = []

        # Find-highlight state. None = no highlight; "match" = this node
        # is one of the search matches; "current" = this node is the
        # currently-cycled match. Set by the canvas via
        # set_find_highlight / clear_find_highlight. Not part of the
        # node's persistent state; cleared when the find bar closes.
        self._find_highlight: str | None = None

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

        # 1. Node body: dark slate fill, uniform rounded rect.
        painter.setBrush(QBrush(self.FILL_COLOR))
        if self.isSelected():
            # Selection wins over find-highlight. A user who has
            # selected a node should see the selection styling
            # regardless of whether the node also happens to be a
            # search match.
            border = QPen(self.BORDER_COLOR_SELECTED, self.BORDER_WIDTH_SELECTED)
        elif self._find_highlight == "current":
            border = QPen(self.FIND_CURRENT_COLOR, self.FIND_BORDER_WIDTH)
        elif self._find_highlight == "match":
            border = QPen(self.FIND_MATCH_COLOR, self.FIND_BORDER_WIDTH)
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

        # 2. Ring-and-icon colour, chosen as the maximum of the device
        # status and the engine's suboptimal severity. This is the single
        # visual channel that reflects "how healthy is this link overall".
        ring_color = self._effective_ring_color()

        ring_cx = self.WIDTH / 2
        ring_cy = 22.0
        ring_radius = self.RING_DIAMETER / 2

        # 2a. Ring interior fill: a very faint tint of the same colour.
        fill = QColor(ring_color)
        fill.setAlpha(self.RING_FILL_ALPHA)
        painter.setBrush(QBrush(fill))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(ring_cx, ring_cy), ring_radius, ring_radius)

        # 2b. Ring stroke: full-opacity, thickened.
        ring_pen = QPen(ring_color, self.RING_STROKE)
        ring_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(ring_cx, ring_cy), ring_radius, ring_radius)

        # 3. Type icon, tinted with the same colour.
        icon_tint = QColor(ring_color)
        icon_tint.setAlpha(self.ICON_TINT_ALPHA)
        pm = icon_pixmap(self.device_type, icon_tint, self.ICON_SIZE)
        icon_x = int(ring_cx - self.ICON_SIZE / 2)
        icon_y = int(ring_cy - self.ICON_SIZE / 2)
        painter.drawPixmap(icon_x, icon_y, pm)

        # 4. Name, bold, centred horizontally, in the lower portion of
        #    the node. The IP is deliberately not shown on the card; it is
        #    available in the tooltip. Keeping the card to a single line
        #    of text keeps the visual weight low and the name prominent.
        name_font = QFont()
        name_font.setPointSize(10)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(QPen(self.NAME_COLOR))

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

    def _effective_ring_color(self) -> QColor:
        """
        Compose the ring-and-icon colour from the two signals that matter:
        the device status and the engine's suboptimality severity.

        Rule: the colour is the maximum of the two. Status is authoritative
        for the strong states (DOWN, DEGRADED, UNKNOWN); when the device is
        UP, suboptimality can promote the colour from green to amber, red,
        or dark red depending on severity.

        Why: a device that is technically reachable but whose link quality
        is degraded should not look identical to a healthy one. The engine
        reports `mild` from around 100 ms latency and `severe` at the same
        point DEGRADED is committed. The ring is the one visual that
        reflects this without needing to read the tooltip.

        Mappings:
            DOWN                                 -> red (override)
            DEGRADED                             -> amber (override)
            UNKNOWN                              -> grey  (override)
            UP + severity none                   -> green
            UP + severity mild / moderate        -> amber
            UP + severity severe                 -> red
            UP + severity critical               -> dark red
        """
        # Status overrides take priority: these are the strongest signals
        # and their colour should not be diluted by suboptimality.
        if self.status == "DOWN":
            return self.RING_COLOR_DOWN
        if self.status == "DEGRADED":
            return self.RING_COLOR_DEGRADED
        if self.status == "UNKNOWN":
            return self.RING_COLOR_UNKNOWN

        # Status is UP (or an unrecognised value): let suboptimality promote
        # the colour. Unknown severities fall through to green so a future
        # engine that reports a new severity degrades to the safest visual.
        severity = self._suboptimal_severity
        if severity == "critical":
            return self.RING_COLOR_CRITICAL
        if severity == "severe":
            return self.RING_COLOR_DOWN
        if severity in ("moderate", "mild"):
            return self.RING_COLOR_DEGRADED
        return self.RING_COLOR_UP

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

        Emits statusChanged after the attribute is updated, so subscribers
        see the new value when they react. ConnectionItem subscribes to
        this so that edges can repaint when their endpoints' statuses
        change — without it, an edge touching a node that just went DOWN
        would keep its pre-transition appearance until something else
        triggered a repaint.
        """
        if status == self.status:
            return
        self.status = status
        self._invalidate_cache()
        self._update_tooltip()
        self.statusChanged.emit(status)

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

    def set_suboptimal(self, severity: str, reasons: list) -> None:
        """
        Set the suboptimality state from a cycle result. Called by the
        canvas's on_cycle_complete slot. Idempotent: no-op if severity and
        reasons are unchanged, so repeated cycles do not thrash the pixmap
        cache.

        `severity` is one of the engine's SuboptimalSeverity values as a
        string: "none", "mild", "moderate", "severe", "critical". Unknown
        values are treated as "none" (no colour promotion), so a future
        engine that reports a new severity degrades to the safest visual.

        The severity affects the ring-and-icon colour via
        _effective_ring_color(). The reasons are shown in the tooltip.
        """
        reasons_list = list(reasons) if reasons else []
        if (
            severity == self._suboptimal_severity
            and reasons_list == self._suboptimal_reasons
        ):
            return
        self._suboptimal_severity = severity or "none"
        self._suboptimal_reasons = reasons_list
        self._invalidate_cache()
        self._update_tooltip()

    def set_find_highlight(self, current: bool) -> None:
        """
        Set the find-highlight state. `current=True` marks this node as
        the currently-cycled match; `current=False` marks it as another
        match in the set. Both states are visually distinct from normal
        selection; the current match is more prominent.

        Called by the canvas's _apply_find_highlight(). Idempotent.
        """
        new_state = "current" if current else "match"
        if self._find_highlight == new_state:
            return
        self._find_highlight = new_state
        self._invalidate_cache()

    def clear_find_highlight(self) -> None:
        """
        Clear any find-highlight state. Called when the search is cleared
        or the find bar closes. Idempotent.
        """
        if self._find_highlight is None:
            return
        self._find_highlight = None
        self._invalidate_cache()

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

        The quality line reflects what the ring colour is currently
        showing, so the two are consistent: if the ring is amber because
        of a mild suboptimality, the tooltip says so; if the device is
        DOWN, the tooltip says DOWN and the quality line is suppressed
        (the DOWN alert takes precedence in the visual narrative).
        """
        latency = (
            f"{self._last_latency_ms:.1f} ms"
            if self._last_latency_ms is not None
            else "—"
        )
        monitoring = "on" if self.monitoring_enabled else "off"

        if self.status in ("DOWN", "UNKNOWN"):
            quality_line = None
        elif self._suboptimal_severity == "none":
            quality_line = "Quality: good"
        elif self._suboptimal_reasons:
            quality_line = (
                f"Quality: {self._suboptimal_severity} — "
                + "; ".join(self._suboptimal_reasons)
            )
        else:
            quality_line = f"Quality: {self._suboptimal_severity}"

        lines = [
            self.name,
            f"IP: {self.ip_address or '(unset)'}",
            f"Type: {self.device_type.label}",
            f"Status: {self.status}",
            f"Latency: {latency}",
            f"Monitoring: {monitoring}",
        ]
        if quality_line is not None:
            lines.append(quality_line)

        self.setToolTip("\n".join(lines))

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