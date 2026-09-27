"""
Connection edge between two DeviceNodes.

An edge is a QGraphicsObject with:
  - a reference to each endpoint node,
  - a subscription to both nodes' positionChanged signals,
  - a geometry that is clipped to the gap between the two node rects
    (so it renders and is clickable only where there is visible space),
  - a z-value of -1 so any residual overlap with a node body is hidden.

Edges never move on their own; they only follow their endpoints. Dragging
an edge is deliberately not supported.

Milestone 4 does not persist edges. They exist only while the app is running.
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

    # Drawn line.
    LINE_WIDTH = 2.0
    LINE_COLOR = QColor("#5f6368")
    LINE_COLOR_SELECTED = QColor("#1a73e8")

    # Hit area. Separate from the drawn width so the edge is clickable
    # without being visually heavy. Because the geometry is clipped to the
    # gap between nodes, this width cannot accidentally swallow clicks on a
    # node body.
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

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            # Deliberately NOT ItemIsMovable. Edges are laid out from their
            # endpoints' positions; allowing the user to drag one would be
            # meaningless and would immediately be overridden on the next
            # node drag.
        )
        self.setZValue(self.Z_VALUE)

        # Subscribe to both endpoints. On any node move, re-lay-out.
        self.from_node.positionChanged.connect(self._on_endpoint_moved)
        self.to_node.positionChanged.connect(self._on_endpoint_moved)

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
        The visible edge: the centre-to-centre line, trimmed at both ends to
        the border of the respective node rect.

        Suppression rule: return None only when the two node *centres* are
        closer than half a node's diagonal, i.e. effectively at the same
        spot, where no meaningful edge exists. Two nodes whose rects merely
        intersect (drawn near each other but not on top of each other) still
        produce an edge; the overlapping portions of the line are hidden
        behind the nodes because the edge is at z=-1.

        An earlier version of this method returned None whenever the two
        node rects intersected. That was too strict: in normal use the user
        places nodes a few dozen pixels apart, their 120x60 rects overlap,
        and the edge was silently suppressed even though the nodes were
        visually distinct and clearly connectable.
        """
        from_rect = self.from_node.rect_in_scene()
        to_rect = self.to_node.rect_in_scene()

        from_centre = self.from_node.scene_centre()
        to_centre = self.to_node.scene_centre()

        dx = to_centre.x() - from_centre.x()
        dy = to_centre.y() - from_centre.y()
        centre_distance = (dx * dx + dy * dy) ** 0.5

        # Half-diagonal of a node rect. For a 120x60 node this is about 67.
        # If centres are closer than that, the nodes are visually stacked
        # and there is no meaningful edge to draw.
        half_diag = (
            (from_rect.width() ** 2 + from_rect.height() ** 2) ** 0.5
        ) / 2.0

        if centre_distance < half_diag:
            return None

        raw = self._raw_line()
        p_start = self._exit_point_of_rect(raw, from_rect)
        p_end = self._exit_point_of_rect(
            QLineF(raw.p2(), raw.p1()), to_rect
        )

        if p_start is None or p_end is None:
            # Nodes are separated, so both clips must succeed. Fall back to
            # the raw line if something unexpected happens (e.g. a future
            # change to anchoring), rather than drawing nothing.
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

        Because the clipped edge lives entirely in the gap between the two
        node rects, clicks that land on a node body cannot select the edge -
        which is what makes dragging a connected node work reliably.
        When there is no meaningful edge (centres coincident), the shape is
        empty and the edge cannot be clicked at all.
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
    # Painting
    # ------------------------------------------------------------------

    def paint(self, painter, option, widget=None):
        clipped = self._clipped_line()
        if clipped is None:
            return

        painter.setRenderHint(painter.RenderHint.Antialiasing, True)

        if self.isSelected():
            pen = QPen(self.LINE_COLOR_SELECTED, self.LINE_WIDTH + 1.0)
        else:
            pen = QPen(self.LINE_COLOR, self.LINE_WIDTH)
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
            # Already disconnected, or the underlying C++ object was deleted.
            pass
        try:
            self.to_node.positionChanged.disconnect(self._on_endpoint_moved)
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