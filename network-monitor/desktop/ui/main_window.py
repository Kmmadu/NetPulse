"""
Main application window.

Milestone 1: title, size, and an empty TopologyCanvas as the central widget.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import Qt

from ui.canvas import TopologyCanvas


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("NetPulse — Network Topology")
        self.resize(1200, 800)

        # Central widget hosts the canvas. We keep a container (rather than
        # setting the canvas directly as central) so later milestones can add
        # a toolbar, side panel or status bar around it without restructuring.
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = TopologyCanvas(container)
        layout.addWidget(self.canvas)

        self.setCentralWidget(container)

        self.statusBar().showMessage("Ready — canvas empty. Milestone 1.")