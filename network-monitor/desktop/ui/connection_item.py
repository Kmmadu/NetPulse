"""
Connection edge between two DeviceNodes.

An edge is a QGraphicsObject with:
  - a reference to each endpoint node,
  - a subscription to both nodes' positionChanged signals,
  - a subscription to both nodes' statusChanged signals,
  - a geometry that is clipped to the gap between the two node rects
    (so it renders and is clickable only where there is visible space),
  - a z-value of -1 so any residual overlap with a node body is hidden.

Edges never move on their own; they only follow their endpoints. Dragging
an edge is deliberately not supported.

Milestone 4 does not persist edges. They exist only while the app is running.

Milestone 7.99: the line colour now reflects the status of its endpoints.
An edge touching a DOWN node is muted red; an edge touching a DEGRADED node
is muted amber; an edge between healthy nodes is muted green; a selected
edge is always bright blue, regardless of endpoint status. The geometry,
hit shape, and lifecycle are unchanged from Milestone 4.

Milestone 7.104 (fix): edges are no longer mouse-interactive. The
ItemIsSelectable flag was removed and setAcceptedMouseButtons(NoButton)
was added. With ItemIsSelectable set, a left-press anywhere inside the
edge's hit-stroke was routed to the edge rather than to the node behind
it; the view then held the mouse grab on the edge, and any node whose
body overlapped the edge's stroke (i.e. any two nodes close enough to
be worth connecting) became undraggable. Edges are still right-clickable
via the canvas context menu, which is the only interaction they need.

Milestone 7.104 (fix): _clipped_line() now only refuses to draw when
the two centres are essentially coincident. The previous threshold was
half the node diagonal (~67 px for a 120x60 node), which suppressed the
edge entirely for two cards placed 60 px apart — a normal arrangement
when connecting nearby devices, and the reason "no visual indication"
was reported after connecting. The fallback to the raw line when the
clip fails also prevents silent suppression when the two rects overlap.
"""

from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QPen, QColor, QPainterPath, QPainterPathStroker
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ui.device_node import DeviceNode


class ConnectionItem(QGraphicsObject):
    """A visual link between two device nodes."""

    # Drawn line geometry. Independent of colour; a selected edge uses
    # LINE_WIDTH + 1.0 as its stroke width.
    LINE_WIDTH = 2.0

    # Line colours. The choice among them is made by _line_color(); see
    # that method for the priority rules.
    #
    # Default, when both endpoints are UP. Muted green, matching the
    # "healthy" colour family of the node ring without being as
    # saturated — the edge is supporting information, and the ring on
    # the nodes is the primary status signal.
    LINE_COLOR = QColor("#2E7D4A")           # muted green
    # Selected, overriding any status tint. (Retained for a future
    # gesture that selects an edge explicitly; not reachable from a
    # left-click today, because edges are not mouse-interactive.)
    LINE_COLOR_SELECTED = QColor("#6B9BFF")  # brighter blue
    # One or both endpoints DOWN.
    LINE_COLOR_DOWN = QColor("#8B3030")      # muted red
    # One or both endpoints DEGRADED.
    LINE_COLOR_DEGRADED = QColor("#8B6A20")  # muted amber

    # Hit area. Kept as a constant because shape() still uses it — even
    # though edges accept no mouse buttons now, a future "select the
    # edge by clicking within 4 px of it" gesture would reuse this.
    HIT_WIDTH = 8.0

    # Drawn behind nodes (nodes are at z=0). With clipping this is belt-and-
    # braces: the clipped segment never overlaps a node body anyway, but a
    # negative z keeps any anti-aliasing bleed from appearing over the node.
    Z_VALUE = -1

    def __init__(self, from_node: "DeviceNode", to_node: "DeviceNode"):
        super().__init__()

        if from_node is to_node:
            raise ValueError("Self-loops are not permitted.")

        self.from_node = from_node
        self.to_node = to_node

        # Edges are deliberately NOT mouse-interactive.
        #
        # The previous version set ItemIsSelectable and left
        # setAcceptedMouseButtons at its default (all buttons). With
        # those, QGraphicsView.itemAt() would return the edge for any
        # press that landed inside the edge's shape() — which, for two
        # nodes placed close enough to connect, includes a band that
        # runs through the overlapping portion of the two node rects.
        # The press was routed to the edge, the view held the mouse
        # grab on the edge, and the node underneath never saw the
        # press: "connected nodes can't be dragged".
        #
        # Removing ItemIsSelectable and refusing all mouse buttons
        # means itemAt() skips the edge for hit-testing purposes and
        # presses always reach the node under the cursor. The edge is
        # still removable via the canvas context menu, which is the
        # only interaction it needs.
        #
        # ItemIsMovable was already correctly absent: edges derive
        # their position from their endpoints, so dragging one is
        # meaningless.
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(self.Z_VALUE)

        # Subscribe to both endpoints. On any node move, re-lay-out.
        self.from_node.positionChanged.connect(self._on_endpoint_moved)
        self.to_node.positionChanged.connect(self._on_endpoint_moved)

        # Subscribe to status changes too, so the edge repaints when either
        # endpoint transitions between UP / DEGRADED / DOWN / UNKNOWN. The
        # colour decision itself happens in paint() by reading the nodes'
        # current statuses; this subscription only forces the repaint.
        self.from_node.statusChanged.connect(self._on_endpoint_status_changed)
        self.to_node.statusChanged.connect(self._on_endpoint_status_changed)

        # Coalescing flag for the deferred geometry update. See
        # _on_endpoint_moved for why the update is deferred.
        self._update_pending = False

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _raw_line(self) -> QLineF:
        """The full centre-to-centre line in scene coordinates.

        Used as the input to clipping and for computing the repaint region
        in boundingRect(). Never drawn directly; paint() draws the clipped
        segment instead.
        """
        return QLineF(
            self.from_node.scene_centre(),
            self.to_node.scene_centre(),
        )

    @staticmethod
    def _exit_point_of_rect(line: QLineF, rect: QRectF) -> Optional[QPointF]:
        """
        Given a line whose *start point* lies inside `rect`, return the
        point at which the line crosses the rectangle's boundary moving
        towards the end point. Returns None if the start is outside the
        rect, or if the line's direction never crosses a boundary.

        This is a specialised Liang-Barsky: we already know the start is
        inside, so we only need the minimum positive t at which the line
        crosses any of the four rectangle edges.
        """
        p1 = line.p1()
        p2 = line.p2()

        if not rect.contains(p1):
            return None

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()

        ts = []

        if dx != 0.0:
            t = (rect.left() - p1.x()) / dx
            if 0.0 < t <= 1.0:
                ts.append(t)
            t = (rect.right() - p1.x()) / dx
            if 0.0 < t <= 1.0:
                ts.append(t)

        if dy != 0.0:
            t = (rect.top() - p1.y()) / dy
            if 0.0 < t <= 1.0:
                ts.append(t)
            t = (rect.bottom() - p1.y()) / dy
            if 0.0 < t <= 1.0:
                ts.append(t)

        if not ts:
            return None

        t_min = min(ts)
        return QPointF(p1.x() + t_min * dx, p1.y() + t_min * dy)

    def _clipped_line(self) -> Optional[QLineF]:
        """
        The visible edge: the centre-to-centre line, trimmed at both ends
        to the border of the respective node rect.

        Suppression rule (revised): return None only when the two node
        *centres* are within LINE_WIDTH of each other — i.e. the two nodes
        are visually stacked and there is no meaningful edge to draw.

        The previous threshold was half the node diagonal, which for a
        120x60 node is ~67 px. That suppressed the edge for any two nodes
        placed within 67 px of each other — a completely normal spacing
        for two nearby cards the user is trying to connect — which is
        why connected nodes sometimes showed no visible line at all.
        Two nodes drawn slightly apart from one another have a meaningful
        edge at any non-zero distance.

        Fallback: if either clip fails (which happens when the two node
        rects overlap such that one centre lies inside the other rect),
        return the raw centre-to-centre line rather than None. The portion
        of the raw line that lies inside a node body is hidden behind that
        node (edge z = -1), so the visible result still reads as a
        connection between the two nodes.
        """
        from_centre = self.from_node.scene_centre()
        to_centre = self.to_node.scene_centre()

        dx = to_centre.x() - from_centre.x()
        dy = to_centre.y() - from_centre.y()
        centre_distance = (dx * dx + dy * dy) ** 0.5

        # Only refuse when the centres are effectively coincident.
        if centre_distance < self.LINE_WIDTH:
            return None

        from_rect = self.from_node.rect_in_scene()
        to_rect = self.to_node.rect_in_scene()

        raw = self._raw_line()
        p_start = self._exit_point_of_rect(raw, from_rect)
        p_end = self._exit_point_of_rect(
            QLineF(raw.p2(), raw.p1()), to_rect
        )

        if p_start is None or p_end is None:
            # Nodes overlap (one centre is inside the other's rect), or
            # the clip otherwise failed. Fall back to the raw line rather
            # than suppressing the edge entirely; the node bodies will
            # cover the portions of the line that pass through them.
            return raw

        return QLineF(p_start, p_end)

    def boundingRect(self) -> QRectF:
        """
        Repaint region for this item: a rectangle covering both endpoints,
        padded by the hit width so the clickable area and anti-aliasing
        bleed are both inside it.

        Uses the raw centre-to-centre extent, not the clipped segment. The
        clipped segment is always a subset of this rectangle, and using the
        raw extent keeps the repaint region stable as the two nodes are
        dragged towards each other.

        Note: QLineF has no boundingRect() method in Qt; the rectangle is
        constructed manually from the two endpoints. This was the source of
        an AttributeError in an earlier version.
        """
        p1 = self._raw_line().p1()
        p2 = self._raw_line().p2()
        pad = self.HIT_WIDTH

        left = min(p1.x(), p2.x()) - pad
        right = max(p1.x(), p2.x()) + pad
        top = min(p1.y(), p2.y()) - pad
        bottom = max(p1.y(), p2.y()) + pad

        return QRectF(left, top, right - left, bottom - top)

    def shape(self) -> QPainterPath:
        """
        Hit-test shape: a stroke around the *clipped* edge only.

        This shape is still consulted by the scene's itemAt() when
        deciding which item is under the cursor. Because edges now
        accept no mouse buttons (see __init__), a press that lands on
        this shape does not select the edge; the scene simply skips
        the edge and considers the next item, which is the node behind
        it. The shape is retained because a future "click to select
        the edge" gesture — if the user wants one — would reuse it,
        and because QGraphicsItem expects a shape() implementation.

        When there is no meaningful edge (centres coincident), the
        shape is empty.
        """
        path = QPainterPath()
        clipped = self._clipped_line()
        if clipped is None:
            return path  # empty path = no hit area

        path.moveTo(clipped.p1())
        path.lineTo(clipped.p2())

        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_WIDTH)
        return stroker.createStroke(path)

    # ------------------------------------------------------------------
    # Colour
    # ------------------------------------------------------------------

    def _line_color(self) -> QColor:
        """
        Choose the line colour based on selection state and the status of
        the two endpoints.

        Priority:
          1. Selection — a selected edge is always the brighter blue,
             regardless of endpoint status, so the user can always see
             what they have selected. (Currently unreachable from a
             left-click, since edges accept no mouse buttons; retained
             for a future explicit-selection gesture.)
          2. DOWN — if either endpoint is DOWN, muted red.
          3. DEGRADED — if either endpoint is DEGRADED, muted amber.
          4. Default — muted green.

        DOWN takes precedence over DEGRADED because a device that is
        unreachable is a stronger signal than a device that is merely
        slow. This mirrors DeviceNode._effective_ring_color()'s
        precedence rules.
        """
        if self.isSelected():
            return self.LINE_COLOR_SELECTED

        statuses = {self.from_node.status, self.to_node.status}
        if "DOWN" in statuses:
            return self.LINE_COLOR_DOWN
        if "DEGRADED" in statuses:
            return self.LINE_COLOR_DEGRADED
        return self.LINE_COLOR

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paint(self, painter, option, widget=None):
        clipped = self._clipped_line()
        if clipped is None:
            return

        painter.setRenderHint(painter.RenderHint.Antialiasing, True)

        colour = self._line_color()
        if self.isSelected():
            pen = QPen(colour, self.LINE_WIDTH + 1.0)
        else:
            pen = QPen(colour, self.LINE_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        painter.drawLine(clipped)

        # Endpoint markers on a selected edge: two filled circles that make
        # "this edge is selected" unambiguous at a glance. Drawn only when
        # selected so the visual weight of the canvas stays low.
        if self.isSelected():
            painter.setBrush(self.LINE_COLOR_SELECTED)
            painter.setPen(Qt.PenStyle.NoPen)
            radius = 4.0
            for point in (clipped.p1(), clipped.p2()):
                painter.drawEllipse(point, radius, radius)

    # ------------------------------------------------------------------
    # Interaction hooks
    # ------------------------------------------------------------------

    def _on_endpoint_moved(self, _new_centre: QPointF) -> None:
        """
        Recompute our geometry when an endpoint moves.

        Called from the node's positionChanged signal, which fires *during*
        the node's drag event dispatch. Calling prepareGeometryChange()
        directly here would mutate the scene's spatial index while the scene
        is mid-drag, and on some Qt versions that resets the drag's mouse
        grab - the node stops following the cursor even though the press was
        registered.

        Fix: defer the geometry update to the next event-loop iteration.
        By then the node's drag event has been fully dispatched, and it is
        safe to update our bounds and repaint. Multiple rapid position
        changes coalesce naturally because we only need the latest position,
        not every intermediate one.
        """
        if self._update_pending:
            return
        self._update_pending = True
        QTimer.singleShot(0, self._deferred_geometry_update)

    def _deferred_geometry_update(self) -> None:
        self._update_pending = False
        self.prepareGeometryChange()
        self.update()

    def _on_endpoint_status_changed(self, _new_status: str) -> None:
        """
        Called when either endpoint's status changes. The only effect is
        to schedule a repaint; the actual colour choice happens in
        paint() by reading the endpoints' current statuses. Keeping the
        decision in paint() means there is one source of truth for
        "what colour is this edge" — the same principle as
        DeviceNode._effective_ring_color().

        Not coalesced through the QTimer used for geometry updates: a
        status change is a single event that arrives at most once per
        monitoring cycle, so the cost of an immediate update() is
        negligible. The QTimer coalescing is for the many-per-second
        position changes during a drag, not for status transitions.
        """
        self.update()

    def detach(self) -> None:
        """
        Disconnect from the endpoint signals. Called by the canvas before an
        edge is removed, so a deleted edge cannot be woken by a node that is
        still being dragged, and so nodes do not retain references to edges
        that no longer exist in the scene.
        """
        try:
            self.from_node.positionChanged.disconnect(self._on_endpoint_moved)
        except (RuntimeError, TypeError):
            pass
        try:
            self.to_node.positionChanged.disconnect(self._on_endpoint_moved)
        except (RuntimeError, TypeError):
            pass
        try:
            self.from_node.statusChanged.disconnect(
                self._on_endpoint_status_changed
            )
        except (RuntimeError, TypeError):
            pass
        try:
            self.to_node.statusChanged.disconnect(
                self._on_endpoint_status_changed
            )
        except (RuntimeError, TypeError):
            pass

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def connects(self, node) -> bool:
        """True if `node` is either endpoint of this edge."""
        return node is self.from_node or node is self.to_node

    def other_end(self, node):
        """Return the endpoint that is not `node`. Caller must ensure
        `node` is one of the endpoints (checked by `connects`)."""
        if node is self.from_node:
            return self.to_node
        if node is self.to_node:
            return self.from_node
        raise ValueError("Node is not an endpoint of this connection.")