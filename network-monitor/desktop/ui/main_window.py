"""
Main application window.

Milestone 6: owns the monitoring QThread and worker, wires the worker's
cycleComplete signal to the canvas, and stops everything cleanly on close.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import QThread, Qt

from ui.canvas import TopologyCanvas
from monitoring_worker import (
    MonitoringWorker,
    PING_COUNT,
    PING_TIMEOUT,
    RETRY_COUNT,
)


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
        #   thread.started       -> worker.on_thread_started  (builds engine, starts timer)
        #   worker.engineReady   -> status bar update
        #   worker.cycleComplete -> canvas.on_cycle_complete (updates node statuses)
        #   worker.registerNode  -> worker.on_register_node
        #   worker.unregisterNode -> worker.on_unregister_node
        #   GUI close            -> worker.on_stop, then thread.quit/wait
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

    def _shutdown_wait_ms(self) -> int:
        """
        Derive the wait timeout for worker-thread shutdown from the ping
        parameters the worker actually uses.

        Why derived: on_stop() can only be delivered *between* cycles, so
        shutdown always waits for at most one full cycle. A full cycle is
        bounded, per device, by RETRY_COUNT * PING_COUNT * PING_TIMEOUT
        seconds. Pings run in parallel across devices, so the bound does
        not multiply by device count. We add a safety buffer and clamp the
        lower bound at 5 seconds so an accidentally-tiny configuration does
        not cause premature terminate() on slow hosts.
        """
        per_device_bound_seconds = RETRY_COUNT * PING_COUNT * PING_TIMEOUT
        buffer_seconds = 5
        total_seconds = per_device_bound_seconds + buffer_seconds
        return max(5000, total_seconds * 1000)

    def closeEvent(self, event) -> None:
        """
        Stop the worker cooperatively, then quit and join the thread.

        Order:
          1. Ask the worker to stop (queued; runs on worker thread).
             Sets the stop flag and stops the timer. Any cycle currently
             in progress runs to completion; no new cycle starts.
          2. Quit the thread's event loop.
          3. Wait for the thread to exit, using a timeout derived from the
             ping parameters. If that wait fails, fall back to terminate()
             — which is documented as unsafe but is still preferable to a
             hung application.

        QThread.terminate() is a real risk when the target thread might be
        running Python bytecode (which it is here whenever a cycle is in
        flight). Forced cancellation can leave the interpreter and CPython
        refcounts in an inconsistent state, which cascades into stray
        exceptions in unrelated slots, dangling glib event sources, and a
        segfault on exit. The wait timeout is sized to make this fallback
        practically unreachable; if it does fire, something is genuinely
        wrong and we accept the risk rather than hang.
        """
        self._worker.stop.emit()

        self._worker_thread.quit()
        wait_ms = self._shutdown_wait_ms()
        if not self._worker_thread.wait(wait_ms):
            print(
                f"[main_window] worker thread did not exit in "
                f"{wait_ms}ms; terminating (this should not happen)"
            )
            self._worker_thread.terminate()
            self._worker_thread.wait(1000)

        super().closeEvent(event)