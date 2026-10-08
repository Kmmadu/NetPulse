"""
Main application window.

Milestone 6: owns the monitoring QThread and worker, wires the worker's
cycleComplete signal to the canvas, and stops everything cleanly on close.

Milestone 7.5: adds SMTP configuration, prompted on first run if alerting
is not configured.

Milestone 7.9: adds canvas zoom controls and Ctrl+0 to reset to 100%.

Milestone 7.95: the zoom controls move into a HeaderBar at the top of the
window. The permanent right-side zoom panel is gone; the canvas occupies
the full width of the central area. The zoom dropdown overlays the canvas
when opened and closes on selection or click-outside. The menu bar is
removed — Settings lives in the header.

Milestone 7.99 (cleanup): the terminate() fallback in closeEvent now uses
a doubled wait timeout with a 30-second floor, so the fallback is reached
only when the environment is genuinely pathological. If it is reached,
the failure is logged loudly to stderr and reported to the user via a
modal dialog before terminate() runs, rather than being a silent print.

Milestone 7.102: adds the find feature's entry points. The header's find
button (header.findRequested) opens the canvas's find bar via
show_find_bar, and Ctrl+F does the same from anywhere in the window.

Milestone 8: wires persistence. Once the worker's engine is up
(engineReady), the worker's Database instance is handed to the canvas
via canvas.set_database(), and the canvas loads the saved topology from
it via canvas.load_topology(). On close, any debounced position changes
still pending are flushed before the worker is stopped, so a drag that
ended less than 500 ms before the window closed is not lost. Nothing in
the shutdown ordering changed; the flush is one line at the top of
closeEvent, before the existing blocking worker stop.

Milestone 8 (view): adds Ctrl+H as the "Home" keyboard shortcut. It
calls canvas.fit_to_window(), the same action as the header's Fit menu
item and the same action the canvas performs automatically after
load_topology(). Three entry points, one method.

Milestone 8 (view, revision): the canvas starts at 75% zoom rather than
100%. On a fresh DB this is the opening state; on a reopen with a saved
topology, the default is immediately overridden by load_topology()'s
auto-fit, so the user always ends up seeing their nodes framed. The
default matters only for the empty-canvas case, where auto-fit has
nothing to fit and would otherwise leave the view at whatever scale the
transform happens to be.
"""

import sys

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMessageBox,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import QThread, Qt, QMetaObject, QTimer

from ui.canvas import TopologyCanvas
from ui.header_bar import HeaderBar
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

        # ------------------------------------------------------------------
        # Central layout: header bar (fixed height) + canvas (fills rest)
        # ------------------------------------------------------------------
        # The header replaces both the previous menu bar and the zoom
        # sidebar. The canvas gets everything below the header, at full
        # width. No sidebar reserves horizontal space.
        self.canvas = TopologyCanvas(self)
        self.header = HeaderBar(self)

        # Default view for a fresh canvas. 75% is small enough that a
        # handful of nodes placed near the origin do not crowd the
        # window, and large enough that the grid and node labels are
        # still legible. Overridden by load_topology()'s auto-fit when
        # there is a saved topology to show; that is the intended
        # precedence — fit-to-topology beats fit-to-default.
        self.canvas.set_zoom(0.75)

        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.header)          # fixed height
        central_layout.addWidget(self.canvas, 1)       # stretch: fills
        self.setCentralWidget(central)

        # Header wiring. The zoom signals keep their old names, so only
        # the receiving widget changed; the connections themselves are
        # otherwise the same as the previous milestone.
        self.header.settingsRequested.connect(self._open_config_dialog)
        self.header.zoomRequested.connect(self.canvas.set_zoom)
        self.header.fitRequested.connect(self.canvas.fit_to_window)
        self.canvas.zoomChanged.connect(self.header.set_current_zoom)

        # Find feature: the header's find button opens the canvas's
        # floating find bar. The bar itself (positioning, focus, match
        # highlighting) is owned by the canvas; MainWindow only wires
        # the button's signal to the canvas's public method.
        self.header.findRequested.connect(self.canvas.show_find_bar)

        # ------------------------------------------------------------------
        # Shortcuts
        # ------------------------------------------------------------------
        # Ctrl+0 resets the canvas zoom to 100%. Application-level so it
        # works regardless of which child widget has focus.
        reset_zoom_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        reset_zoom_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        reset_zoom_shortcut.activated.connect(self.canvas.reset_zoom)

        # Ctrl+F opens the find bar. Application-level so it works from
        # anywhere in the window, including when the canvas has focus.
        find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        find_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        find_shortcut.activated.connect(self.canvas.show_find_bar)

        # Ctrl+H fits the view to the current topology — the "Home"
        # action. Same as the "Fit" entry at the top of the header's
        # zoom menu. Application-level so it works regardless of focus.
        #
        # Ctrl+H is chosen because it is unused elsewhere and its
        # mnemonic ("H" for Home) is natural. Ctrl+0 is already taken by
        # reset-to-100%-at-origin, which is a different operation: it
        # snaps the transform to identity, whereas Fit computes a scale
        # from the node bounding box. Both are useful; neither replaces
        # the other.
        fit_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        fit_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        fit_shortcut.activated.connect(self.canvas.fit_to_window)

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
        #   worker.engineReady   -> status bar update + persistence setup
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

        # Persistence wiring (Milestone 8). When the worker's engine is
        # ready, hand the canvas its Database and load the saved topology
        # from it. The engineReady signal fires from the worker thread;
        # the slot runs on the GUI thread via Qt's automatic queued
        # dispatch. That ordering is why we connect here and not earlier:
        # until engineReady fires, self._worker._engine is None and there
        # is no Database to hand over.
        self._worker.engineReady.connect(
            self._on_engine_ready_for_persistence
        )

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

    def _on_engine_ready_for_persistence(self) -> None:
        """
        Hand the worker's Database to the canvas and load the saved
        topology.

        The Database instance is shared with the worker thread. That is
        safe: Database uses threading.local for its connections, so the
        GUI thread lazily creates and configures its own SQLite
        connection on first access. No locking or handoff is required.

        Called once, from the GUI thread, when the worker's engineReady
        signal fires — at which point self._worker._engine exists and
        self._worker.get_database() returns a live Database.

        If get_database() returns None (should not happen given the
        engineReady contract), persistence is disabled for this session
        and a warning is printed. The rest of the app still works.
        """
        db = self._worker.get_database()
        if db is None:
            print(
                "[main_window] engineReady fired but worker has no DB; "
                "persistence disabled for this session.",
                file=sys.stderr,
            )
            return

        self.canvas.set_database(db)
        self.canvas.load_topology()

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
          0. Flush any pending debounced position saves. This is a
             Milestone 8 addition and must happen before the worker is
             stopped, because the flush writes through the Database
             instance and we want that write to complete while the
             application is still live. flush_pending_saves() is a
             no-op if nothing is pending and a no-op if persistence
             was never enabled.
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
          3. Wait for the thread to exit, using a generously derived
             timeout. If the wait fails, fall back to terminate(), which
             is documented as unsafe but is still preferable to a hung
             application.

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

        On the terminate() fallback: QThread.terminate() is documented as
        unsafe and can, if called while the target thread is executing
        Python bytecode or a C extension, corrupt the interpreter state
        and produce a SIGSEGV on exit. The wait timeout above is derived
        from the ping parameters and then doubled with a 30-second floor,
        which makes reaching this fallback in practice a sign that
        something is genuinely wrong — likely a kernel-level network
        freeze or a subprocess that will never return. If it is reached,
        it is logged loudly to stderr and reported to the user via a
        modal dialog so the failure is not silent.
        """

        # Persistence flush. Before the worker stops, so the write goes
        # through a live Database instance rather than racing teardown.
        self.canvas.flush_pending_saves()

        QMetaObject.invokeMethod(
            self._worker,
            "on_stop",
            Qt.ConnectionType.BlockingQueuedConnection,
        )

        self._worker_thread.quit()

        # The derived timeout is generous on its own; doubling it and
        # imposing a 30-second floor makes the fallback reachable only
        # when the environment is genuinely pathological. This is
        # deliberate: the alternative — a tighter timeout that fires
        # sometimes — would put the unsafe terminate() path on the
        # routine path, which is exactly what the shutdown redesign was
        # meant to eliminate.
        wait_ms = max(30_000, self._shutdown_wait_ms() * 2)

        if not self._worker_thread.wait(wait_ms):
            # Reaching this branch means the worker thread did not exit
            # within the (very generous) timeout. Log loudly and warn the
            # user before doing anything drastic, so the failure is
            # visible rather than silent.
            print(
                f"[SHUTDOWN-FAILURE] worker thread did not exit in "
                f"{wait_ms}ms; forcing termination. This indicates the "
                f"derived timeout was wrong for this environment. "
                f"Please report this.",
                file=sys.stderr,
                flush=True,
            )
            QMessageBox.warning(
                self,
                "Shutdown problem",
                "The monitoring worker thread did not stop cleanly within "
                f"{wait_ms // 1000} seconds and was forcibly terminated.\n\n"
                "The application will now exit, but this indicates a "
                "problem with the environment that may cause unreliable "
                "shutdown behaviour.\n\n"
                "If you can, please note what was happening at the time "
                "(very slow network? a device that never responds?) and "
                "report it.",
            )
            self._worker_thread.terminate()
            self._worker_thread.wait(1000)

        super().closeEvent(event)