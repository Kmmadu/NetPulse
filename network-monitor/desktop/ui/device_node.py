"""
Device node — the visual representation of a single device on the canvas.

Milestone 4: becomes a signal source for position changes so connected
edges can re-lay-out as the node is dragged. Adds connection_anchor()
and rect_in_scene() so edges can clip to the node's border.
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


class DeviceNode(QGraphicsObject):
    """A movable, selectable, deletable device node with a device type."""

    # Emitted whenever the node's position changes in scene coordinates.
    # ConnectionItem subscribes to this so that edges follow the node during
    # drags. Emitted from itemChange().
    positionChanged = Signal(QPointF)

    WIDTH = 120
    HEIGHT = 60
    CORNER_RADIUS = 8

    BORDER_COLOR = QColor("#1a73e8")
    BORDER_COLOR_SELECTED = QColor("#0b47a1")
    TEXT_COLOR = QColor("#202124")
    GLYPH_COLOR = QColor("#3c4043")

    def __init__(
        self,
        name: str = "device",
        position: QPointF = None,
        device_type: DeviceType = DeviceType.GENERIC,
    ):
        super().__init__()

        self.device_id: str = str(uuid.uuid4())
        self.name: str = name
        self.device_type: DeviceType = device_type

        self._rect = QRectF(0, 0, self.WIDTH, self.HEIGHT)

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setZValue(0)

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
        painter.setBrush(QBrush(self.device_type.fill))

        if self.isSelected():
            pen = QPen(self.BORDER_COLOR_SELECTED, 2.5)
        else:
            pen = QPen(self.BORDER_COLOR, 1.5)
        painter.setPen(pen)

        painter.drawRoundedRect(
            self._rect, self.CORNER_RADIUS, self.CORNER_RADIUS
        )

        glyph_font = QFont()
        glyph_font.setPointSize(8)
        glyph_font.setBold(True)
        painter.setFont(glyph_font)
        painter.setPen(QPen(self.GLYPH_COLOR))

        glyph_rect = QRectF(
            self._rect.left() + 6,
            self._rect.top() + 4,
            40,
            16,
        )
        painter.drawText(
            glyph_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.device_type.glyph,
        )

        name_font = QFont()
        name_font.setPointSize(10)
        painter.setFont(name_font)
        painter.setPen(QPen(self.TEXT_COLOR))

        name_rect = self._rect.adjusted(6, 10, -6, -6)
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignCenter,
            self.name,
        )

    # ------------------------------------------------------------------
    # QGraphicsItem hooks
    # ------------------------------------------------------------------

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()

        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Emit the *new* scene-centre so subscribers get a ready-to-use
            # anchor point. Qt fires this change many times per drag; each
            # emission wakes the connected ConnectionItems, which each do a
            # cheap line update.
            self.positionChanged.emit(self.scene_centre())

        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        # Reserved for Milestone 5's edit dialog.
        event.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_device_type(self, device_type: DeviceType) -> None:
        if device_type == self.device_type:
            return
        self.device_type = device_type
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

    def centre(self) -> QPointF:
        return self._rect.center()

    def scene_centre(self) -> QPointF:
        return self.mapToScene(self._rect.center())

    def connection_anchor(self) -> QPointF:
        """
        The point in scene coordinates where connections attach.

        Kept for symmetry with rect_in_scene(); the current ConnectionItem
        implementation clips to the node's rectangle rather than anchoring
        at the centre, but this method is still useful for any future
        caller that wants a single reference point on the node.
        """
        return self.scene_centre()

    def rect_in_scene(self) -> QRectF:
        """
        The node's bounding rectangle, in scene coordinates.

        Used by ConnectionItem to clip edge endpoints to the node's border
        rather than the centre, so that only the segment of the edge that
        lies in the visible gap between two nodes is drawn and clickable.

        The node is axis-aligned (ItemIsMovable, no rotation or shear), so
        mapping the two opposite corners is sufficient and exact.
        """
        top_left = self.mapToScene(self._rect.topLeft())
        bottom_right = self.mapToScene(self._rect.bottomRight())
        return QRectF(top_left, bottom_right)