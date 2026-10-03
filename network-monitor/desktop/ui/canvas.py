"""
Topology canvas — the central drawing surface for the network map.

Milestone 6: registers created nodes with the monitoring worker, unregisters
deleted nodes, and updates each node's status ring from the worker's
cycle results.
"""

from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QMenu,
)
from PySide6.QtCore import Qt, QPointF, Slot
from PySide6.QtGui import QPainter, QKeyEvent, QContextMenuEvent, QCursor

from ui.device_node import DeviceNode
from ui.connection_item import ConnectionItem
from ui.device_types import DeviceType
from ui.device_dialog import DeviceDialog


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

        self._connections: list[ConnectionItem] = []
        self._connect_source: DeviceNode | None = None

        # Set by attach_worker() at MainWindow construction. Until then the
        # canvas operates in "no monitoring" mode (all nodes UNKNOWN).
        self._worker = None

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

        Results are dicts produced by MonitoringEngine.check_all_devices().
        Fields we use:
          device_id        -> matches DeviceNode.device_id
          current_status   -> "UP" | "DEGRADED" | "DOWN" | "UNKNOWN"
          latency_ms       -> optional; stored on the node for the tooltip
          ping_details     -> optional dict with min/max/packet_loss
        """
        # Build a lookup for O(n) rather than O(n*m).
        by_id = {
            item.device_id: item
            for item in self._scene.items()
            if isinstance(item, DeviceNode)
        }

        for result in results:
            device_id = result.get("device_id")
            node = by_id.get(device_id)
            if node is None:
                # The device exists in the engine but not on the canvas;
                # most likely a node that was just deleted and whose
                # unregister signal has not yet been processed by the
                # worker. Skip silently.
                continue

            status = result.get("current_status")
            if isinstance(status, str):
                node.set_status(status)

            # Populate tooltip data. Latency may be None for DOWN devices;
            # set_latency handles that.
            node.set_latency(result.get("latency_ms"))

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

        # Register with the worker if monitoring is enabled for this node.
        # The worker will skip it if the engine is not yet up (registration
        # is queued and applied once on_thread_started runs).
        if self._worker is not None and monitoring_enabled and ip_address:
            self._worker.registerNode.emit(node.device_id, node.name, node.ip_address)

        return node

    def _on_node_double_clicked(self, node: DeviceNode) -> None:
        self.edit_device(node)

    def edit_device(self, node: DeviceNode) -> None:
        """
        Open the edit dialog seeded with the node's current values. If the
        user accepts, apply the changes to the node and, if necessary,
        re-register or unregister it with the worker (name or IP change,
        or monitoring enabled/disabled).
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

        # Inform the worker of the change. The simplest correct approach:
        # unregister and re-register if anything relevant changed. The
        # unregister slot is a queued signal, so it will run between
        # worker events and cannot race the timer.
        if self._worker is not None:
            relevant_change = (
                old_ip != node.ip_address
                or old_monitoring != node.monitoring_enabled
                or old_name != node.name
            )
            if relevant_change:
                self._worker.unregisterNode.emit(node.device_id)
                if node.monitoring_enabled and node.ip_address:
                    self._worker.registerNode.emit(
                        node.device_id, node.name, node.ip_address
                    )

    # ------------------------------------------------------------------
    # Connection operations (unchanged from Milestone 5)
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
            # Unregister from the worker first so it stops pinging the
            # device on its next cycle.
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
    # Connection mode (unchanged)
    # ------------------------------------------------------------------

    def _begin_connect(self, source: DeviceNode) -> None:
        self._connect_source = source
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _cancel_connect(self) -> None:
        self._connect_source = None
        self.unsetCursor()

    def mousePressEvent(self, event) -> None:
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

    # ------------------------------------------------------------------
    # Context menu (unchanged, plus the edit action from Milestone 5)
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
    # Keyboard (unchanged)
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
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