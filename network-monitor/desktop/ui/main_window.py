"""
Main application window.

Milestone 6: owns the monitoring QThread and worker, wires the worker's
cycleComplete signal to the canvas, and stops everything cleanly on close.

Milestone 7.5: adds a Settings menu with SMTP Configuration, and prompts
for SMTP configuration on first run if alerting is not configured.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QMessageBox
from PySide6.QtGui import QAction
from PySide6.QtCore import QThread, Qt, QMetaObject, QTimer

from ui.canvas import TopologyCanvas
from ui.config_dialog import ConfigDialog
from ui import config_manager
from monitoring_worker import (
    MonitoringWorker,
    PING_COUNT,
    PING_TIMEOUT,
    RETRY_COUNT,
    INTERVAL_SECONDS,
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
        # Menu bar
        # ------------------------------------------------------------------
        # Only one menu for now: Settings, with SMTP Configuration. Future
        # milestones may add entries here (log retention, theme, etc.); the
        # menu is a QMenuBar so adding them is a one-line change.
        settings_menu = self.menuBar().addMenu("&Settings")
        smtp_action = QAction("&SMTP Configuration…", self)
        smtp_action.triggered.connect(self._open_config_dialog)
        settings_menu.addAction(smtp_action)

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
        #   thread.started       -> worker.on_thread_started
        #   worker.engineReady   -> status bar update
        #   worker.cycleComplete -> canvas.on_cycle_complete
        #   worker.registerNode  -> worker.on_register_node
        #   worker.unregisterNode -> worker.on_unregister_node
        #   GUI close            -> worker.on_stop (blocking), then thread.quit/wait
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
        # First-run prompt for SMTP configuration
        # ------------------------------------------------------------------
        # Deferred via a single-shot timer so it runs after the event loop
        # has started and the window is shown. Opening a modal dialog
        # during __init__ (before show()) can behave oddly on some
        # platforms, notably Wayland; deferring is cheap and reliable.
        QTimer.singleShot(500, self._prompt_for_config_if_needed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_engine_ready(self) -> None:
        self.statusBar().showMessage(
            f"Monitoring active — cycle interval {INTERVAL_SECONDS}s."
        )

    # ------------------------------------------------------------------
    # SMTP configuration
    # ------------------------------------------------------------------

    def _prompt_for_config_if_needed(self) -> None:
        """
        Open the SMTP config dialog on startup if alerting is not already
        configured. If it is configured, do nothing.
        """
        if config_manager.is_alerting_configured():
            return
        self.statusBar().showMessage(
            "SMTP is not configured — alerting disabled.", 5000
        )
        self._open_config_dialog()

    def _open_config_dialog(self) -> None:
        """
        Open the SMTP config dialog, and if the user accepts, write the
        values to desktop/.env and apply them to the running process. The
        status bar reports the outcome; the dialog reports nothing itself
        once it has closed.
        """
        dialog = ConfigDialog(self)
        if dialog.exec() != ConfigDialog.DialogCode.Accepted:
            return

        try:
            config_manager.write_env(dialog.values)
            config_manager.apply_to_process()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Configuration save failed",
                f"Could not write SMTP configuration:\n\n{exc}",
            )
            return

        if config_manager.is_alerting_configured():
            self.statusBar().showMessage(
                "SMTP configuration saved and verified.", 5000
            )
        else:
            self.statusBar().showMessage(
                "SMTP configuration saved, but the connection test failed.",
                5000,
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

        Order and mechanism:
          1. Invoke worker.on_stop BLOCKING on the worker thread. This
             runs the timer stop + deleteLater + reference drop to
             completion before we return, so the worker's QTimer is
             actually gone by the time the thread's event loop exits.
             This is the difference between a clean shutdown and one
             where the QTimer survives to be finalized by the main
             thread during interpreter teardown, producing the
             "QObject::killTimer: Timers cannot be stopped from another
             thread" warnings.
          2. Quit the thread's event loop.
          3. Wait for the thread to exit, using a timeout derived from
             the ping parameters. If that wait fails, fall back to
             terminate(), which is documented as unsafe but is still
             preferable to a hung application.

        Why BlockingQueuedConnection and not a signal emit: emitting a
        queued signal returns immediately and the queued slot invocation
        is merely *enqueued* on the worker thread's event queue. A
        subsequent thread.quit() is also enqueued. There is no ordering
        guarantee between the two beyond FIFO, and more importantly no
        guarantee that the stop slot has actually *run* by the time the
        thread's event loop processes the quit. A race is possible in
        which quit is processed first and the timer is left un-stopped.
        BlockingQueuedConnection removes the race: the caller waits until
        the slot has finished executing on the worker thread.

        BlockingQueuedConnection must not be used between objects on the
        same thread (it deadlocks). Here the caller is the GUI thread and
        the callee lives on the worker thread, so it is the correct
        mechanism.
        """
        QMetaObject.invokeMethod(
            self._worker,
            "on_stop",
            Qt.ConnectionType.BlockingQueuedConnection,
        )

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