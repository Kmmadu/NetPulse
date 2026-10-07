"""
Topology canvas — the central drawing surface for the network map.

Milestone 6: registers created nodes with the monitoring worker, unregisters
deleted nodes, and updates each node's status ring from the worker's
cycle results.

Milestone 7.75: forwards the engine's per-cycle suboptimal report to each
node so it can promote its ring colour when link quality is degraded.

Milestone 7.85: editing a device's IP or name re-registers it without
unregistering first, so the engine's Device object (and its state-machine
memory) survives an edit.

Milestone 7.9: adds Ctrl+wheel zoom around the mouse cursor, Ctrl+0 to
reset to 100%, middle-button drag to pan, a `zoomChanged` signal, and
a `fit_to_window` method. Grid lines are now very faint and their alpha
is scaled by zoom level so they fade almost entirely when zoomed out.

Milestone 7.9 (revision): grid colour and alpha tuned; zoom API
(`set_zoom`, `zoom_level`, `fit_to_window`) added to support a side
panel of preset zoom buttons.

Milestone 7.96: canvas background changed from white to a dark graphite
(#0F1117), and the grid recalibrated for the dark background. Every
fifth grid line is drawn slightly brighter than the others, giving the
technical-mesh feel called for in the redesign brief. No interaction
logic changed.

Milestone 7.102: adds a find bar, opened with Ctrl+F or the header's
find button. Typing filters nodes by case-insensitive name substring;
matches get a yellow border, the current match an orange one; navigation
with Enter / Shift+Enter or the bar's ▲ ▼ buttons. The bar is a
floating overlay parented to the viewport; while it is active the
canvas's own key handlers (Delete, Esc) are suppressed so the user can
type without deleting the selected node.

Milestone 7.102 (revision): the find bar now follows the view. It
subscribes to the two scrollbars' valueChanged signals and to
zoomChanged, and repositions itself to the top-centre of the current
viewport on every change. Without this, panning or zooming would move
the scene under a stationary overlay and the bar would visually drift
away from the top of what the user is looking at.
"""

from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QMenu,
)
from PySide6.QtCore import Qt, QPointF, QPoint, QRectF, Slot, Signal
from PySide6.QtGui import (
    QPainter, QKeyEvent, QContextMenuEvent, QCursor,
    QWheelEvent, QMouseEvent, QColor,
)

from ui.device_node import DeviceNode
from ui.connection_item import ConnectionItem
from ui.device_types import DeviceType
from ui.device_dialog import DeviceDialog
from ui.find_bar import FindBar


class TopologyCanvas(QGraphicsView):
    """Scrollable / zoomable view of a QGraphicsScene holding the topology."""

    SCENE_WIDTH = 4000
    SCENE_HEIGHT = 4000

    # Zoom bounds and per-notch step.
    MIN_ZOOM = 0.25
    MAX_ZOOM = 4.0
    ZOOM_STEP = 1.15

    # Canvas background. Dark graphite: dark enough to feel like an IDE
    # or a NOC tool, not so dark that it reads as pure black. This is the
    # canvas's substrate; every node and edge is drawn on top of it.
    BACKGROUND_COLOR = QColor("#0F1117")

    # Grid appearance. Recalibrated for the dark background: the grid
    # is a lighter graphite drawn at low alpha. Still a placement aid,
    # not a visual feature — node visibility takes priority.
    #
    # Every Nth grid line is drawn at a slightly higher alpha to give the
    # mesh a technical rhythm without making any line loud. The pitch is
    # the number of regular steps between accent lines.
    GRID_BASE_COLOR = QColor(26, 29, 36)      # #1A1D24, dark graphite
    GRID_ACCENT_COLOR = QColor(40, 44, 54)    # #282C36, slightly brighter
    GRID_ACCENT_PITCH = 5                     # every 5th line is an accent

    # Grid line alpha, expressed as a function of zoom. The values below
    # define a linear ramp: at MIN_ZOOM alpha = 8 (essentially invisible),
    # at 100% alpha = 40 (faint but present), at MAX_ZOOM alpha = 60
    # (slightly stronger so precise alignment work stays easy).
    GRID_ALPHA_AT_MIN_ZOOM = 8
    GRID_ALPHA_AT_100 = 40
    GRID_ALPHA_AT_MAX_ZOOM = 60

    # Emitted whenever the effective zoom level changes. Value is the
    # current scale as a float (1.0 == 100%). Used by the header bar to
    # keep the Zoom button's label in sync with Ctrl+wheel changes.
    zoomChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(0, 0, self.SCENE_WIDTH, self.SCENE_HEIGHT)
        self.setScene(self._scene)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(self.BACKGROUND_COLOR)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._grid_step = 25

        self._node_counter = 0

        self._connections: list[ConnectionItem] = []
        self._connect_source: DeviceNode | None = None

        # Set by attach_worker() at MainWindow construction. Until then the
        # canvas operates in "no monitoring" mode (all nodes UNKNOWN).
        self._worker = None

        # Middle-button pan state.
        self._pan_active = False
        self._pan_last_pos: QPoint | None = None

        # ------------------------------------------------------------------
        # Find bar
        # ------------------------------------------------------------------
        # The find bar is a floating overlay parented to the viewport,
        # like the (now reverted) tool palette was. It is hidden by
        # default; MainWindow calls show_find_bar() when the user presses
        # Ctrl+F or clicks the find button in the header.
        #
        # State:
        #   self._find_bar           — the widget
        #   self._find_bar_active    — True while visible and focused;
        #                              checked at the top of keyPressEvent
        #                              so the canvas does not process its
        #                              own key bindings (Delete, Esc, etc.)
        #                              while the user is typing a search.
        #   self._find_matches       — the current list of matched nodes,
        #                              in scene order.
        #   self._find_current_index — index into _find_matches for the
        #                              currently-cycled match.
        self._find_bar = FindBar(self.viewport())
        self._find_bar.hide()
        self._find_bar.queryChanged.connect(self._on_find_query_changed)
        self._find_bar.nextRequested.connect(self._on_find_next)
        self._find_bar.previousRequested.connect(self._on_find_previous)
        self._find_bar.closedRequested.connect(self.hide_find_bar)

        self._find_bar_active = False
        self._find_matches: list = []
        self._find_current_index: int = 0

        # Reposition the find bar whenever the view's transform or scroll
        # position changes. The bar is parented to the viewport, so it
        # keeps its pixel position when the scene moves under it — which
        # means it drifts visually away from the top of what the user is
        # looking at. Subscribing to the scrollbars' valueChanged and to
        # zoomChanged and calling the same _reposition_find_bar keeps the
        # bar anchored to the top-centre of the *current* view.
        #
        # The guard inside _on_view_changed (bar is visible) keeps the
        # cost zero when the find feature is not in use.
        self.horizontalScrollBar().valueChanged.connect(self._on_view_changed)
        self.verticalScrollBar().valueChanged.connect(self._on_view_changed)
        self.zoomChanged.connect(self._on_view_changed)

    # ------------------------------------------------------------------
    # Worker attachment
    # ------------------------------------------------------------------

    def attach_worker(self, worker) -> None:
        """
        Give the canvas a reference to the monitoring worker so it can
        register / unregister nodes via the worker's signals. Called once
        by MainWindow before the thread starts.
        """
        self._worker = worker

    @Slot(list)
    def on_cycle_complete(self, results: list) -> None:
        """
        GUI-thread slot: update every node from the worker's per-cycle results.
        See earlier milestone docstrings for the field list; unchanged here.
        """
        by_id = {
            item.device_id: item
            for item in self._scene.items()
            if isinstance(item, DeviceNode)
        }

        for result in results:
            device_id = result.get("device_id")
            node = by_id.get(device_id)
            if node is None:
                continue

            status = result.get("current_status")
            if isinstance(status, str):
                node.set_status(status)

            node.set_latency(result.get("latency_ms"))

            suboptimal = result.get("suboptimal") or {}
            if isinstance(suboptimal, dict):
                severity = suboptimal.get("severity", "none")
                reasons = suboptimal.get("reasons", [])
                if not isinstance(reasons, list):
                    reasons = []
                node.set_suboptimal(severity, reasons)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Ctrl+wheel zooms; plain wheel scrolls (Qt's default).
        """
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            steps = 1 if delta > 0 else -1
            self._apply_zoom(steps)
            event.accept()
            return

        super().wheelEvent(event)

    def _apply_zoom(self, steps: int) -> None:
        """
        Multiply the current scale by ZOOM_STEP per step, clamped to
        [MIN_ZOOM, MAX_ZOOM]. `steps` is positive to zoom in, negative to
        zoom out.
        """
        current = self.transform().m11()
        factor = self.ZOOM_STEP ** steps
        target = current * factor
        self._set_scale(target)

    def set_zoom(self, scale: float) -> None:
        """
        Public API: set zoom to a specific scale (1.0 == 100%). Clamped
        to [MIN_ZOOM, MAX_ZOOM]. Used by the header bar's zoom menu.

        Resets the transform to identity before applying the target
        scale, so repeated calls do not accumulate drift and the result
        is exactly the requested scale (subject to clamping).
        """
        self._set_scale(scale)

    def zoom_level(self) -> float:
        """Return the current scale as a float (1.0 == 100%)."""
        return self.transform().m11()

    def reset_zoom(self) -> None:
        """
        Snap back to 100% scale and centre the view on the scene origin.
        Bound to Ctrl+0.
        """
        self.resetTransform()
        self.horizontalScrollBar().setValue(0)
        self.verticalScrollBar().setValue(0)
        self.zoomChanged.emit(self.transform().m11())

    def fit_to_window(self) -> None:
        """
        Compute the bounding box of all DeviceNode items in the scene,
        choose the scale that fits that box in the current viewport with
        a small margin, clamp to [MIN_ZOOM, MAX_ZOOM], apply it, and
        centre the view on the box.

        If there are no nodes, do nothing — the canvas is empty and there
        is nothing to fit.

        Also used by the header bar's "Fit" menu item.
        """
        nodes = [
            item for item in self._scene.items()
            if isinstance(item, DeviceNode)
        ]
        if not nodes:
            return

        # Bounding rect in scene coordinates. rect_in_scene returns the
        # node's axis-aligned rectangle in scene coords; union of those
        # is the topology's extent.
        bounds = QRectF()
        first = True
        for node in nodes:
            r = node.rect_in_scene()
            if first:
                bounds = r
                first = False
            else:
                bounds = bounds.united(r)

        if bounds.width() <= 0 or bounds.height() <= 0:
            return

        # Available area in the viewport, with a small margin so nodes
        # do not touch the edges.
        margin = 40
        viewport_w = max(1, self.viewport().width() - margin * 2)
        viewport_h = max(1, self.viewport().height() - margin * 2)

        scale_x = viewport_w / bounds.width()
        scale_y = viewport_h / bounds.height()
        target = min(scale_x, scale_y)

        # Clamp.
        if target < self.MIN_ZOOM:
            target = self.MIN_ZOOM
        elif target > self.MAX_ZOOM:
            target = self.MAX_ZOOM

        self.resetTransform()
        self.scale(target, target)
        self.centerOn(bounds.center())

        self.zoomChanged.emit(self.transform().m11())

    def _set_scale(self, target: float) -> None:
        """
        Shared implementation for `_apply_zoom`, `set_zoom`, and any
        other path that wants to move the scale to a specific value.
        Clamps, resets the transform, applies the new scale, and emits
        zoomChanged if the value actually changed.

        Anchoring under the mouse is a property of the transformation
        anchor, not of this method; callers that want cursor-anchored
        zoom have already set the anchor to AnchorUnderMouse in __init__.
        """
        current = self.transform().m11()

        if target < self.MIN_ZOOM:
            target = self.MIN_ZOOM
        elif target > self.MAX_ZOOM:
            target = self.MAX_ZOOM

        if abs(target - current) < 1e-6:
            return

        self.resetTransform()
        self.scale(target, target)
        self.zoomChanged.emit(target)

    # ------------------------------------------------------------------
    # Pan
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = True
            self._pan_last_pos = event.pos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
            return

        if self._connect_source is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                scene_pos = self.mapToScene(event.pos())
                item = self._scene.itemAt(scene_pos, self.transform())

                if isinstance(item, DeviceNode):
                    self.add_connection(self._connect_source, item)
                self._cancel_connect()
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self._cancel_connect()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pan_active and self._pan_last_pos is not None:
            delta = event.pos() - self._pan_last_pos
            self._pan_last_pos = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_active:
            self._pan_active = False
            self._pan_last_pos = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Background
    # ------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect) -> None:
        """
        Draw the placement grid on the dark canvas.

        Two grid layers:

          - Regular lines at GRID_BASE_COLOR, at an alpha that ramps from
            GRID_ALPHA_AT_MIN_ZOOM up to GRID_ALPHA_AT_MAX_ZOOM as the
            user zooms in. Fainter when zoomed out so the grid does not
            dominate small nodes; slightly stronger when zoomed in so
            precise alignment work is easy.
          - Every GRID_ACCENT_PITCH-th line at GRID_ACCENT_COLOR, at a
            fixed offset above the regular alpha. This gives the mesh a
            technical rhythm — the "blueprint" feel — without making any
            individual line loud.

        The alpha ramp logic is unchanged from Milestone 7.9; only the
        colours and the two-layer draw are new.
        """
        super().drawBackground(painter, rect)

        # Compute the base alpha for the current scale. Same linear ramp
        # as Milestone 7.9 — fainter when zoomed out, stronger when zoomed
        # in. The absolute values were chosen for the pale-grey grid; they
        # work equally well for the graphite grid because the alpha, not
        # the colour, is what governs perceived intensity.
        scale = self.transform().m11()
        if scale <= 1.0:
            t = (scale - self.MIN_ZOOM) / (1.0 - self.MIN_ZOOM)
            t = max(0.0, min(1.0, t))
            alpha = int(round(
                self.GRID_ALPHA_AT_MIN_ZOOM
                + t * (self.GRID_ALPHA_AT_100 - self.GRID_ALPHA_AT_MIN_ZOOM)
            ))
        else:
            t = (scale - 1.0) / (self.MAX_ZOOM - 1.0)
            t = max(0.0, min(1.0, t))
            alpha = int(round(
                self.GRID_ALPHA_AT_100
                + t * (self.GRID_ALPHA_AT_MAX_ZOOM - self.GRID_ALPHA_AT_100)
            ))

        base_colour = QColor(self.GRID_BASE_COLOR)
        base_colour.setAlpha(alpha)

        accent_colour = QColor(self.GRID_ACCENT_COLOR)
        # Accent lines are always somewhat brighter than regular lines,
        # regardless of zoom. The offset is fixed rather than ramped so
        # the accent/regular contrast stays consistent at every zoom.
        accent_colour.setAlpha(min(255, alpha + 22))

        painter.save()
        pen = painter.pen()
        pen.setWidth(0)  # cosmetic: 1px on screen regardless of zoom

        step = self._grid_step
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)

        # --- Accent lines first, so regular lines can be drawn on top
        #     if they overlap. (They do not overlap in practice — accent
        #     lines sit on top of regular grid coordinates by design — but
        #     drawing accent first keeps the ordering explicit.)
        pen.setColor(accent_colour)
        painter.setPen(pen)

        x = left
        while x < rect.right():
            # Is this line an accent line? The grid is anchored at the
            # scene origin, so the test is on the scene-coordinate line
            # index, not the pixel x.
            if (x // step) % self.GRID_ACCENT_PITCH == 0:
                painter.drawLine(x, rect.top(), x, rect.bottom())
            x += step

        y = top
        while y < rect.bottom():
            if (y // step) % self.GRID_ACCENT_PITCH == 0:
                painter.drawLine(rect.left(), y, rect.right(), y)
            y += step

        # --- Regular lines on top of the accent lines. Any accent line
        #     that coincides with a regular line is drawn twice at the
        #     accent alpha (since both passes hit it). That is fine: the
        #     second draw simply redraws the same pixel at the same colour.
        pen.setColor(base_colour)
        painter.setPen(pen)

        x = left
        while x < rect.right():
            if (x // step) % self.GRID_ACCENT_PITCH != 0:
                painter.drawLine(x, rect.top(), x, rect.bottom())
            x += step

        y = top
        while y < rect.bottom():
            if (y // step) % self.GRID_ACCENT_PITCH != 0:
                painter.drawLine(rect.left(), y, rect.right(), y)
            y += step

        painter.restore()

    # ------------------------------------------------------------------
    # Scene accessor
    # ------------------------------------------------------------------

    def scene(self) -> QGraphicsScene:
        return self._scene

    # ------------------------------------------------------------------
    # Find
    # ------------------------------------------------------------------

    def show_find_bar(self) -> None:
        """
        Show the find bar and give it focus. Called by MainWindow when
        the user presses Ctrl+F or clicks the find button in the header.
        Idempotent.
        """
        self._find_bar.show()
        self._find_bar.raise_()
        self._find_bar.focus_input()
        self._find_bar_active = True
        self._reposition_find_bar()
        # Re-run the query against the current text so re-opening the
        # bar with a stale query re-highlights the matches. If the
        # input was cleared by hide_find_bar, this is a no-op.
        self._on_find_query_changed(self._find_bar.query())

    def hide_find_bar(self) -> None:
        """
        Hide the find bar, clear its query, and clear all highlights.
        Called by MainWindow when Esc is pressed outside the bar, or by
        the bar itself when the user clicks its close button or presses
        Esc inside it.
        """
        self._find_bar.hide()
        self._find_bar.clear()
        self._find_bar_active = False
        self._clear_find_matches()

    def _on_find_query_changed(self, text: str) -> None:
        """
        Recompute the match set in response to a keystroke in the find
        input. Updates the highlight on every node and refreshes the
        counter in the bar.
        """
        self._find_matches = self.find_nodes(text)
        self._find_current_index = 0
        self._apply_find_highlight()

        if self._find_matches:
            self._centre_on_find_match()
            self._find_bar.set_match_info(1, len(self._find_matches))
        else:
            self._find_bar.set_match_info(0, 0)

    def _on_find_next(self) -> None:
        """Cycle to the next match, wrapping around."""
        if not self._find_matches:
            return
        self._find_current_index = (
            self._find_current_index + 1
        ) % len(self._find_matches)
        self._apply_find_highlight()
        self._centre_on_find_match()
        self._find_bar.set_match_info(
            self._find_current_index + 1, len(self._find_matches)
        )

    def _on_find_previous(self) -> None:
        """Cycle to the previous match, wrapping around."""
        if not self._find_matches:
            return
        self._find_current_index = (
            self._find_current_index - 1
        ) % len(self._find_matches)
        self._apply_find_highlight()
        self._centre_on_find_match()
        self._find_bar.set_match_info(
            self._find_current_index + 1, len(self._find_matches)
        )

    def _apply_find_highlight(self) -> None:
        """
        Push the current find state onto every node: matched nodes get
        a highlight; unmatched nodes have any prior highlight cleared;
        the current match gets the "current" treatment.
        """
        match_set = set(self._find_matches)
        current_node = (
            self._find_matches[self._find_current_index]
            if self._find_matches else None
        )

        for item in self._scene.items():
            if not isinstance(item, DeviceNode):
                continue
            if item in match_set:
                item.set_find_highlight(current=(item is current_node))
            else:
                item.clear_find_highlight()

    def _clear_find_matches(self) -> None:
        """Remove any find highlight from every node. Called when the
        find bar closes."""
        for item in self._scene.items():
            if isinstance(item, DeviceNode):
                item.clear_find_highlight()
        self._find_matches = []
        self._find_current_index = 0

    def _centre_on_find_match(self) -> None:
        """
        Pan the view so the current match is visible. Per design decision
        D4, we only pan when the node is not already fully inside the
        current viewport — a match that is already visible is left where
        the user can see it.
        """
        if not self._find_matches:
            return
        node = self._find_matches[self._find_current_index]
        node_rect = node.rect_in_scene()
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        if visible.contains(node_rect):
            return
        self.centerOn(node_rect.center())

    def _on_view_changed(self, *_args) -> None:
        """
        Called when the view's zoom or scroll changes. Repositions the
        find bar if it is visible, so it stays anchored to the top-centre
        of the viewport.

        Accepts a variable number of positional arguments because it is
        connected to two different signals: scrollbar.valueChanged(int)
        and zoomChanged(float). The arguments are ignored; the reposition
        reads the current viewport size and computes the position from
        scratch.

        Guarded on the bar being visible so the cost is zero when the
        find feature is not in use. This fires on every scroll step
        during a pan, so keeping the guard is what makes the subscription
        cheap.
        """
        if self._find_bar.isVisible():
            self._reposition_find_bar()

    def _reposition_find_bar(self) -> None:
        """
        Position the find bar centred horizontally, 12 px below the top
        of the viewport. Called on show, on viewport resize, and on every
        view change (scroll or zoom) via _on_view_changed.

        The horizontal centring and top offset are recomputed from the
        current viewport size every time, so there is no state to keep in
        sync between callers.
        """
        viewport = self.viewport()
        self._find_bar.adjustSize()

        x = (viewport.width() - self._find_bar.width()) // 2

        # Keep the bar near the top; clamp to the viewport if the window
        # is unusually short, so the bar does not get pushed off the
        # visible area.
        y = 12
        max_y = viewport.height() - self._find_bar.height() - 4
        if max_y >= 0 and y > max_y:
            y = max_y

        self._find_bar.move(x, y)

    def resizeEvent(self, event) -> None:
        """
        Reposition the find bar when the viewport is resized. Called by
        Qt on every viewport resize; keeps the bar's horizontal
        centring correct as the window changes size.
        """
        super().resizeEvent(event)
        if self._find_bar is not None:
            self._reposition_find_bar()

    def find_nodes(self, query: str) -> list:
        """
        Return the nodes whose name contains `query` as a substring,
        case-insensitively. An empty or whitespace-only query returns
        an empty list, so a fresh find bar does not highlight every
        node on the canvas.

        Order is stable: nodes are returned in the order they appear
        in the scene's item list, which for practical purposes is the
        order they were added. When the user cycles through matches,
        they move through that order.
        """
        q = query.strip().lower()
        if not q:
            return []
        return [
            item for item in self._scene.items()
            if isinstance(item, DeviceNode) and q in item.name.lower()
        ]

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_device_node(
        self,
        scene_pos: QPointF = None,
        name: str = None,
        device_type: DeviceType = DeviceType.GENERIC,
        ip_address: str = "",
        monitoring_enabled: bool = True,
    ) -> DeviceNode:
        self._node_counter += 1
        if name is None:
            name = f"device-{self._node_counter}"

        if scene_pos is None:
            scene_pos = self.mapToScene(self.viewport().rect().center())

        node = DeviceNode(
            name=name,
            ip_address=ip_address,
            device_type=device_type,
            monitoring_enabled=monitoring_enabled,
        )
        node.setPos(
            scene_pos - QPointF(DeviceNode.WIDTH / 2, DeviceNode.HEIGHT / 2)
        )
        node.doubleClicked.connect(self._on_node_double_clicked)

        self._scene.addItem(node)

        if self._worker is not None and monitoring_enabled and ip_address:
            self._worker.registerNode.emit(
                node.device_id, node.name, node.ip_address
            )

        return node

    def _on_node_double_clicked(self, node: DeviceNode) -> None:
        self.edit_device(node)

    def edit_device(self, node: DeviceNode) -> None:
        """
        Open the edit dialog seeded with the node's current values.
        Re-registration semantics: see Milestone 7.85 docstring.
        """
        old_ip = node.ip_address
        old_monitoring = node.monitoring_enabled
        old_name = node.name

        dialog = DeviceDialog(
            self,
            title=f"Edit '{node.name}'",
            name=node.name,
            ip_address=node.ip_address,
            device_type=node.device_type,
            monitoring_enabled=node.monitoring_enabled,
        )
        if dialog.exec() != DeviceDialog.DialogCode.Accepted:
            return

        node.name = dialog.name
        node.ip_address = dialog.ip_address
        node.set_device_type(dialog.device_type)
        node.set_monitoring_enabled(dialog.monitoring_enabled)
        node._invalidate_cache()

        if self._worker is None:
            return

        monitoring_was_on = old_monitoring
        monitoring_is_on = node.monitoring_enabled

        if monitoring_was_on and not monitoring_is_on:
            self._worker.unregisterNode.emit(node.device_id)
            return

        if monitoring_is_on and node.ip_address:
            if (
                not monitoring_was_on
                or old_ip != node.ip_address
                or old_name != node.name
            ):
                self._worker.registerNode.emit(
                    node.device_id, node.name, node.ip_address
                )

    # ------------------------------------------------------------------
    # Connection operations
    # ------------------------------------------------------------------

    def _find_existing_connection(self, a: DeviceNode, b: DeviceNode):
        for conn in self._connections:
            if (
                (conn.from_node is a and conn.to_node is b)
                or (conn.from_node is b and conn.to_node is a)
            ):
                return conn
        return None

    def add_connection(
        self, from_node: DeviceNode, to_node: DeviceNode
    ) -> ConnectionItem | None:
        if from_node is to_node:
            return None
        if self._find_existing_connection(from_node, to_node) is not None:
            return None

        conn = ConnectionItem(from_node, to_node)
        self._scene.addItem(conn)
        self._connections.append(conn)
        return conn

    def _remove_connection(self, conn: ConnectionItem) -> None:
        conn.detach()
        if conn in self._connections:
            self._connections.remove(conn)
        self._scene.removeItem(conn)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_selected_items(self) -> int:
        selected = self._scene.selectedItems()

        selected_nodes = [it for it in selected if isinstance(it, DeviceNode)]
        selected_edges = [it for it in selected if isinstance(it, ConnectionItem)]

        removed = 0

        for node in selected_nodes:
            for conn in list(self._connections):
                if conn.connects(node):
                    self._remove_connection(conn)
                    removed += 1

        for node in selected_nodes:
            if self._worker is not None:
                self._worker.unregisterNode.emit(node.device_id)
            self._scene.removeItem(node)
            removed += 1

        for conn in selected_edges:
            if conn in self._connections:
                self._remove_connection(conn)
                removed += 1

        return removed

    # ------------------------------------------------------------------
    # Connection mode
    # ------------------------------------------------------------------

    def _begin_connect(self, source: DeviceNode) -> None:
        self._connect_source = source
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _cancel_connect(self) -> None:
        self._connect_source = None
        self.unsetCursor()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if self._connect_source is not None:
            self._cancel_connect()
            event.accept()
            return

        scene_pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(scene_pos, self.transform())

        menu = QMenu(self)

        if isinstance(item, ConnectionItem):
            if not item.isSelected():
                self._scene.clearSelection()
                item.setSelected(True)

            act_delete = menu.addAction("Delete connection")
            chosen = menu.exec(event.globalPos())
            if chosen == act_delete:
                self.delete_selected_items()
            return

        if isinstance(item, DeviceNode):
            if not item.isSelected():
                self._scene.clearSelection()
                item.setSelected(True)

            act_edit = menu.addAction(f"Edit '{item.name}'…")
            act_connect = menu.addAction(f"Start connection from '{item.name}'")

            change_menu = menu.addMenu("Change type")
            for dtype in DeviceType:
                act = change_menu.addAction(dtype.label)
                act.setCheckable(True)
                act.setChecked(dtype == item.device_type)
                act.setData(dtype)

            menu.addSeparator()
            act_delete = menu.addAction(f"Delete '{item.name}'")

            chosen = menu.exec(event.globalPos())
            if chosen is None:
                return
            if chosen == act_edit:
                self.edit_device(item)
                return
            if chosen == act_connect:
                self._begin_connect(item)
                return
            if chosen == act_delete:
                self.delete_selected_items()
                return
            data = chosen.data()
            if isinstance(data, DeviceType):
                item.set_device_type(data)
            return

        add_menu = menu.addMenu("Add device node")
        for dtype in DeviceType:
            act = add_menu.addAction(dtype.label)
            act.setData(dtype)

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        data = chosen.data()
        if isinstance(data, DeviceType):
            self._add_device_via_dialog(scene_pos, data)

    def _add_device_via_dialog(
        self, scene_pos: QPointF, device_type: DeviceType
    ) -> None:
        self._node_counter += 1
        suggested_name = f"device-{self._node_counter}"
        dialog = DeviceDialog(
            self,
            title="Add device",
            name=suggested_name,
            ip_address="",
            device_type=device_type,
            monitoring_enabled=True,
        )
        if dialog.exec() != DeviceDialog.DialogCode.Accepted:
            self._node_counter -= 1
            return

        self.add_device_node(
            scene_pos=scene_pos,
            name=dialog.name,
            device_type=dialog.device_type,
            ip_address=dialog.ip_address,
            monitoring_enabled=dialog.monitoring_enabled,
        )

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._find_bar_active:
            # The find bar has keyboard focus; let the focused widget
            # handle the key. QGraphicsView's default handling would
            # otherwise process Delete and remove the selected node
            # while the user types.
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Escape and self._connect_source is not None:
            self._cancel_connect()
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            removed = self.delete_selected_items()
            if removed:
                event.accept()
                return

        super().keyPressEvent(event)