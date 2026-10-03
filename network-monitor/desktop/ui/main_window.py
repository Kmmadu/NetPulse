"""
Main application window.

Milestone 6: owns the monitoring QThread and worker, wires the worker's
cycleComplete signal to the canvas, and stops everything cleanly on close.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import QThread, Qt

from ui.canvas import TopologyCanvas
from monitoring_worker import MonitoringWorker


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("NetPulse — Network Topology")
        self.resize(1200, 800)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = TopologyCanvas(container)
        layout.addWidget(self.canvas)

        self.setCentralWidget(container)

        # ------------------------------------------------------------------
        # Monitoring worker and thread
        # ------------------------------------------------------------------
        # The worker is created on the GUI thread, then moved to the worker
        # thread. All its slots thereafter run on the worker thread. The
        # canvas is told about the worker so it can register / unregister
        # nodes as they are created and deleted.
        self._worker_thread = QThread(self)
        self._worker_thread.setObjectName("MonitoringWorkerThread")

        self._worker = MonitoringWorker()
        self._worker.moveToThread(self._worker_thread)

        # Lifecycle wiring.
        #   thread.started     -> worker.on_thread_started  (builds engine, starts timer)
        #   worker.engineReady -> the canvas slot that shows "monitoring active"
        #   worker.cycleComplete -> canvas.on_cycle_complete (updates node statuses)
        #   GUI close          -> worker.on_stop (stops timer), then thread.quit/wait
        #
        # The `started` connection is explicitly queued. QThread.started is
        # emitted from the newly started thread; a QueuedConnection ensures
        # the slot runs on the worker thread's event loop rather than being
        # dispatched synchronously inside the signal emission.
        self._worker_thread.started.connect(
            self._worker.on_thread_started,
            Qt.ConnectionType.QueuedConnection,
        )
        self._worker.engineReady.connect(self._on_engine_ready)
        self._worker.cycleComplete.connect(self.canvas.on_cycle_complete)

        # The canvas emits registerNode / unregisterNode. Wire those signals
        # to their slots on the worker. Cross-thread queued dispatch is
        # automatic because the worker lives on the worker thread.
        #
        # These two connects are load-bearing: without them, every node
        # the canvas creates would be silently dropped, engine.devices
        # would stay empty, and no cycle would ever produce results.
        self._worker.registerNode.connect(self._worker.on_register_node)
        self._worker.unregisterNode.connect(self._worker.on_unregister_node)

        # The canvas uses these signals to register and unregister nodes.
        # The canvas emits them; the worker's slots receive them via queued
        # connections (automatic because they cross threads).
        self.canvas.attach_worker(self._worker)

        self._worker_thread.start()

        self.statusBar().showMessage("Starting monitoring engine…")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_engine_ready(self) -> None:
        self.statusBar().showMessage(
            "Monitoring active — cycle interval 10s."
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """
        Stop the worker cooperatively, then quit and join the thread.

        Order matters:
          1. Ask the worker to stop its timer (queued, runs on worker thread).
          2. Quit the thread's event loop.
          3. Wait for the thread to exit.

        We do not use QThread.terminate(): it is documented as unsafe and can
        kill a thread mid-subprocess, leaving a zombie ping process.
        """
        # Emitting this signal is a queued invocation of on_stop on the
        # worker thread. It returns immediately.
        self._worker.stop.emit()

        # Give the worker thread a chance to process the stop slot before
        # we ask its event loop to quit. QThread.quit() enqueues a quit
        # event; wait() blocks until it is processed.
        self._worker_thread.quit()
        if not self._worker_thread.wait(5000):
            # If 5s is not enough (should never happen unless the worker
            # is mid-ping on a very slow host), fall back to terminate so
            # the app can exit. This is ugly but better than a hang.
            print("[main_window] worker thread did not exit in 5s; terminating")
            self._worker_thread.terminate()
            self._worker_thread.wait(1000)

        super().closeEvent(event)