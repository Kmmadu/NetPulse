"""
Topology canvas — the central drawing surface for the network map.

Milestone 4: connection mode, edge lifecycle management, and updated
delete semantics (deleting a node also deletes its edges).
"""

from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QMenu,
)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QKeyEvent, QContextMenuEvent, QCursor

from ui.device_node import DeviceNode
from ui.connection_item import ConnectionItem
from ui.device_types import DeviceType


class TopologyCanvas(QGraphicsView):
    """Scrollable / zoomable view of a QGraphicsScene holding the topology."""

    SCENE_WIDTH = 4000
    SCENE_HEIGHT = 4000

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
        self.setBackgroundBrush(Qt.GlobalColor.white)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._grid_step = 25
        self._grid_color = Qt.GlobalColor.lightGray

        self._node_counter = 0

        # Edge registry. Kept separate from the scene's item list so that
        # deletion and lookup are O(edges) rather than scanning all items,
        # and so that edges can be reasoned about as a distinct collection.
        self._connections: list[ConnectionItem] = []

        # Connection-mode state. None means "normal interaction".
        # A non-None value is the source node whose edge is being drawn.
        self._connect_source: DeviceNode | None = None

    # ------------------------------------------------------------------
    # Background
    # ------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect) -> None:
        super().drawBackground(painter, rect)

        painter.save()
        pen = painter.pen()
        pen.setColor(self._grid_color)
        pen.setWidth(0)
        painter.setPen(pen)

        step = self._grid_step
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)

        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += step

        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += step

        painter.restore()

    # ------------------------------------------------------------------
    # Scene accessor
    # ------------------------------------------------------------------

    def scene(self) -> QGraphicsScene:
        return self._scene

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_device_node(
        self,
        scene_pos: QPointF = None,
        name: str = None,
        device_type: DeviceType = DeviceType.GENERIC,
    ) -> DeviceNode:
        self._node_counter += 1
        if name is None:
            name = f"device-{self._node_counter}"

        if scene_pos is None:
            scene_pos = self.mapToScene(self.viewport().rect().center())

        node = DeviceNode(name=name, device_type=device_type)
        node.setPos(
            scene_pos - QPointF(DeviceNode.WIDTH / 2, DeviceNode.HEIGHT / 2)
        )
        self._scene.addItem(node)
        return node

    # ------------------------------------------------------------------
    # Connection operations
    # ------------------------------------------------------------------

    def _find_existing_connection(self, a: DeviceNode, b: DeviceNode):
        """Return the existing edge between a and b, or None. Direction-
        agnostic: A→B and B→A are considered the same connection."""
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
        """
        Create an edge between two distinct nodes.

        Refuses (returns None, no error) if:
          - the nodes are the same (self-loop),
          - a connection already exists between them (parallel edge).
        """
        if from_node is to_node:
            return None
        if self._find_existing_connection(from_node, to_node) is not None:
            return None

        conn = ConnectionItem(from_node, to_node)
        self._scene.addItem(conn)
        self._connections.append(conn)
        return conn

    def _remove_connection(self, conn: ConnectionItem) -> None:
        """Remove a single edge from the scene and the registry, and detach
        its signals so it cannot be woken later."""
        conn.detach()
        if conn in self._connections:
            self._connections.remove(conn)
        self._scene.removeItem(conn)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_selected_items(self) -> int:
        """
        Delete every selected node and/or edge.

        Ordering matters: when a node is deleted, all edges touching it must
        be removed first. Otherwise we would be left with edges referencing a
        node that is no longer in the scene, and the next drag of any *other*
        node would try to lay out an edge whose endpoint's scene position is
        undefined.
        """
        selected = self._scene.selectedItems()

        selected_nodes = [it for it in selected if isinstance(it, DeviceNode)]
        selected_edges = [it for it in selected if isinstance(it, ConnectionItem)]

        removed = 0

        # First pass: for each selected node, remove every edge touching it.
        for node in selected_nodes:
            for conn in list(self._connections):
                if conn.connects(node):
                    self._remove_connection(conn)
                    removed += 1

        # Second pass: remove nodes.
        for node in selected_nodes:
            self._scene.removeItem(node)
            removed += 1

        # Third pass: remove any remaining selected edges.
        for conn in selected_edges:
            if conn in self._connections:
                self._remove_connection(conn)
                removed += 1

        return removed

    # ------------------------------------------------------------------
    # Connection mode
    # ------------------------------------------------------------------

    def _begin_connect(self, source: DeviceNode) -> None:
        """Enter connection mode with `source` as the origin."""
        self._connect_source = source
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _cancel_connect(self) -> None:
        self._connect_source = None
        self.unsetCursor()

    def mousePressEvent(self, event) -> None:
        # If we are in connection mode, a left-click resolves the target.
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
                # Right-click cancels without creating.
                self._cancel_connect()
                event.accept()
                return

        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        # A right-click while in connection mode cancels the pending connect
        # instead of opening a menu.
        if self._connect_source is not None:
            self._cancel_connect()
            event.accept()
            return

        scene_pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(scene_pos, self.transform())

        menu = QMenu(self)

        # --- Case 1: right-click on a connection edge ---
        if isinstance(item, ConnectionItem):
            if not item.isSelected():
                self._scene.clearSelection()
                item.setSelected(True)

            act_delete = menu.addAction("Delete connection")
            chosen = menu.exec(event.globalPos())
            if chosen == act_delete:
                self.delete_selected_items()
            return

        # --- Case 2: right-click on a node ---
        if isinstance(item, DeviceNode):
            if not item.isSelected():
                self._scene.clearSelection()
                item.setSelected(True)

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

        # --- Case 3: empty canvas ---
        add_menu = menu.addMenu("Add device node")
        for dtype in DeviceType:
            act = add_menu.addAction(dtype.label)
            act.setData(dtype)

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        data = chosen.data()
        if isinstance(data, DeviceType):
            self.add_device_node(scene_pos=scene_pos, device_type=data)

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Esc cancels a pending connection.
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