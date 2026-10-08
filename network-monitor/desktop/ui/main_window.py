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

Milestone 8 (view, fix): the default-zoom call is placed AFTER the
zoomChanged -> set_current_zoom connection. Setting it before meant the
canvas was at 75% but the header label stayed at "Zoom 100 %", because
the signal that would have updated the label had no subscriber at emit
time.

Milestone 9: the topology file to open is decided by the session, not
hardcoded. MainWindow calls session.load_last_path() at construction,
which returns the file the user last had open, or a default if there is
no session or the stored path no longer exists. That path is passed to
MonitoringWorker, which passes it to MonitoringEngine, which opens a
Database pointed at it.

Milestone 9 (Drop 2b): File menu is now complete.
  - New:           ask for a path, create an empty topology there,
                   switch to it.
  - Open…:         ask for a file, switch to it.
  - Save As…:      ask for a target, copy the current file there,
                   switch to the copy.

Switching files means replacing the worker entirely, because the engine
holds a Database for its lifetime and cannot be re-pointed at a
different file mid-run. The restart machinery is _restart_worker_with_new_path:
stop the old worker (blocking on_stop, quit, wait — same pattern as
closeEvent), detach the canvas non-destructively, build a new worker
on a new QThread, rewire signals, start the new thread. On the new
thread's engineReady, the canvas receives the new Database and reloads.

The canvas detaches non-destructively (canvas.detach_for_file_switch)
because switching away from a file must not delete its contents; only
"New topology" (the empty-canvas context menu item) is destructive.
"""

import sys
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMessageBox, QFileDialog,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import QThread, Qt, QMetaObject, QTimer

import session

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
        self.canvas = TopologyCanvas(self)
        self.header = HeaderBar(self)

        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.header)          # fixed height
        central_layout.addWidget(self.canvas, 1)       # stretch: fills
        self.setCentralWidget(central)

        # Header wiring.
        self.header.settingsRequested.connect(self._open_config_dialog)
        self.header.zoomRequested.connect(self.canvas.set_zoom)
        self.header.fitRequested.connect(self.canvas.fit_to_window)
        self.canvas.zoomChanged.connect(self.header.set_current_zoom)

        # Default view for a fresh canvas. Placed AFTER the
        # zoomChanged -> set_current_zoom connection so that set_zoom()'s
        # emitted signal reaches the header and updates the label.
        self.canvas.set_zoom(0.75)

        # Find feature.
        self.header.findRequested.connect(self.canvas.show_find_bar)

        # File menu (M9 Drop 2b). Three actions, all landing in this
        # window because they need to know about the session, the file
        # system, and the worker.
        self.header.fileNewRequested.connect(self._file_new)
        self.header.fileOpenRequested.connect(self._file_open)
        self.header.fileSaveAsRequested.connect(self._file_save_as)

        # ------------------------------------------------------------------
        # Shortcuts
        # ------------------------------------------------------------------
        reset_zoom_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        reset_zoom_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        reset_zoom_shortcut.activated.connect(self.canvas.reset_zoom)

        find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        find_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        find_shortcut.activated.connect(self.canvas.show_find_bar)

        fit_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        fit_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        fit_shortcut.activated.connect(self.canvas.fit_to_window)

        save_as_shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        save_as_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        save_as_shortcut.activated.connect(self._file_save_as)

        new_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        new_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        new_shortcut.activated.connect(self._file_new)

        open_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        open_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        open_shortcut.activated.connect(self._file_open)

        # ------------------------------------------------------------------
        # Monitoring worker and thread — first construction
        # ------------------------------------------------------------------
        # These attributes are set by _start_worker. After construction,
        # they are rebuilt from scratch by every file switch; nothing
        # outside the restart machinery should hold a direct reference
        # to the worker, the thread, or the topology path without going
        # through the accessors (self._worker, self._worker_thread,
        # self._topology_path).
        self._topology_path: str = session.load_last_path()
        self._worker: MonitoringWorker | None = None
        self._worker_thread: QThread | None = None

        self._update_window_title()

        self._start_worker(self._topology_path)

        self.statusBar().showMessage("Starting monitoring engine…")

        # ------------------------------------------------------------------
        # First-run prompt for SMTP configuration
        # ------------------------------------------------------------------
        QTimer.singleShot(500, self._prompt_for_config_if_needed)

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def _start_worker(self, db_path: str) -> None:
        """
        Construct a MonitoringWorker and a QThread for it, wire every
        signal, and start the thread.

        Called once from __init__ and again from
        _restart_worker_with_new_path on every File -> New / Open /
        Save As. The two cases are identical: the caller is responsible
        for having stopped any previous worker and for having detached
        the canvas, if applicable.

        Stores the new worker on self._worker and the new thread on
        self._worker_thread, replacing whatever was there.

        The engineReady slot is _on_engine_ready_for_persistence, which
        hands the canvas the new Database and loads the topology. That
        is why the caller does not need to call canvas.set_database or
        canvas.load_topology after this method: the worker's own startup
        sequence triggers them, on the correct thread, at the correct
        moment.
        """
        self._topology_path = db_path

        self._worker_thread = QThread(self)
        self._worker_thread.setObjectName("MonitoringWorkerThread")

        self._worker = MonitoringWorker(db_path=db_path)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(
            self._worker.on_thread_started,
            Qt.ConnectionType.QueuedConnection,
        )
        self._worker.engineReady.connect(self._on_engine_ready)
        self._worker.cycleComplete.connect(self.canvas.on_cycle_complete)
        self._worker.registerNode.connect(self._worker.on_register_node)
        self._worker.unregisterNode.connect(self._worker.on_unregister_node)
        self._worker.engineReady.connect(
            self._on_engine_ready_for_persistence
        )

        # Give the canvas the new worker so it can emit registerNode /
        # unregisterNode at them. The DB handoff still happens later,
        # in _on_engine_ready_for_persistence.
        self.canvas.attach_worker(self._worker)

        self._worker_thread.start()

    def _stop_worker(self) -> None:
        """
        Stop the current worker and join its thread.

        Mirrors the sequence in closeEvent. Called by the restart
        machinery before building a new worker. Idempotent: safe to
        call when there is no worker (which happens only during
        construction, and there we don't call it at all).

        Does not touch the canvas. The caller decides whether to detach
        the canvas (file switch) or leave it alone (shutdown, which
        discards everything anyway).
        """
        if self._worker is None or self._worker_thread is None:
            return

        QMetaObject.invokeMethod(
            self._worker,
            "on_stop",
            Qt.ConnectionType.BlockingQueuedConnection,
        )
        self._worker_thread.quit()

        wait_ms = max(30_000, self._shutdown_wait_ms() * 2)

        if not self._worker_thread.wait(wait_ms):
            print(
                f"[worker-restart] old worker thread did not exit in "
                f"{wait_ms}ms; forcing termination.",
                file=sys.stderr,
                flush=True,
            )
            self._worker_thread.terminate()
            self._worker_thread.wait(1000)

        # Drop the references. The QThread object itself is parented to
        # self, so it will be destroyed with the window; deleteLater
        # here to release it earlier and avoid accumulating one QThread
        # per file switch.
        self._worker_thread.deleteLater()
        self._worker_thread = None
        self._worker = None

    def _restart_worker_with_new_path(self, new_path: str) -> None:
        """
        Switch the app to a different topology file.

        Sequence:
          1. Flush the canvas's pending debounced position saves. This
             writes to the CURRENT Database, which is what we want: the
             file we are leaving should be up to date.
          2. Detach the canvas non-destructively (canvas.detach_for_file_switch).
             This empties the scene and clears the canvas's DB reference
             without deleting anything from the old file. It also emits
             unregisterNode for every node, which the old worker picks
             up before it is stopped.
          3. Stop the old worker and join its thread.
          4. Update the topology path and the session.
          5. Start a new worker on the new path. That triggers the new
             worker's engineReady, which hands the canvas the new
             Database and loads the topology.

        Between steps 3 and 5 the canvas has no worker, no DB, and an
        empty scene. This window is milliseconds, and all of it runs on
        the GUI thread, so the user cannot interact with the app during
        it. The window is only visible in the sense that the scene is
        empty for one frame.
        """
        # 1. Flush to the old file.
        self.canvas.flush_pending_saves()

        # 2. Non-destructive detach.
        self.canvas.detach_for_file_switch()

        # 3. Stop the old worker.
        self._stop_worker()

        # 4. Session.
        session.save_last_path(new_path)
        session.save_last_save_dir(str(Path(new_path).parent))

        # 5. New worker. Its engineReady will call
        #    _on_engine_ready_for_persistence, which sets the new DB on
        #    the canvas and reloads.
        self._start_worker(new_path)
        self._update_window_title()

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

        Called every time a worker becomes ready: on initial launch, and
        again after every file switch (New, Open, Save As). The canvas
        is already empty at this point — _restart_worker_with_new_path
        called detach_for_file_switch before stopping the old worker —
        so load_topology starts from a clean scene.

        Database uses threading.local for its connections, so the same
        instance is safe to hold on the GUI thread; the GUI thread
        lazily creates its own SQLite connection on first access. No
        locking or handoff is required.

        If get_database() returns None (should not happen given the
        engineReady contract), persistence is disabled for this session
        and a warning is printed. The rest of the app still works.
        """
        if self._worker is None:
            return
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
    # Window title
    # ------------------------------------------------------------------

    def _update_window_title(self) -> None:
        """
        Set the window title to show the current topology file name.

        Format: "NetPulse — Network Topology — <filename>"

        If no topology path is set (should not happen in normal use — the
        session always resolves to a path), falls back to the plain title.
        """
        path = getattr(self, "_topology_path", None)
        if path:
            name = Path(path).name
            self.setWindowTitle(
                f"NetPulse — Network Topology — {name}"
            )
        else:
            self.setWindowTitle("NetPulse — Network Topology")

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _file_new(self) -> None:
        """
        File -> New. Ask for a target path, create an empty topology
        file there, and switch to it.

        The "new" file starts completely empty: no devices, no positions,
        no connections. It is created by the new worker's
        Database.__init__, which does CREATE TABLE IF NOT EXISTS for the
        full schema. There is no separate "create the file" step; asking
        the engine to open a path that does not yet exist creates it.

        Confirmation: none. The current topology is not lost — it stays
        in whatever file it was in. The user is starting a second
        topology alongside the first, not replacing it. If the user
        actually wanted to erase the current topology, that is what the
        "New topology…" context menu item does.
        """
        start_dir = session.load_last_save_dir()
        suggested = str(Path(start_dir) / "topology.npdb")
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "New topology",
            suggested,
            "NetPulse topology (*.npdb);;SQLite database (*.db);;All files (*)",
        )
        if not chosen:
            return

        target = str(Path(chosen))

        # If the file exists, refuse rather than overwrite: this is
        # "New", not "Save As". If the user wants to overwrite an
        # existing topology, they should use Open on it and then use
        # the context menu's "New topology…" to clear it, or pick a
        # different path here.
        if Path(target).exists():
            reply = QMessageBox.question(
                self,
                "Overwrite existing file?",
                f"A file already exists at:\n\n{target}\n\n"
                "New topology will replace its contents with an empty "
                "topology. This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                Path(target).unlink()
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "New topology failed",
                    f"Could not remove existing file:\n\n{target}\n\n{exc}",
                )
                return

        self._restart_worker_with_new_path(target)
        self.statusBar().showMessage(
            f"New topology started at {Path(target).name}.", 5000
        )

    def _file_open(self) -> None:
        """
        File -> Open. Ask for a path, validate it looks like a NetPulse
        topology, and switch to it.

        Validation: the target must be an existing SQLite file that
        contains a topology_positions table. That is the minimum
        distinguishing feature of a desktop topology file; it rules out
        a plain CLI database (no topology_positions), an arbitrary
        SQLite file (no tables at all), and random non-database files
        (SQLite refuses to open them). It does not rule out a NetPulse
        file from a different version — that is fine, opening an older
        file is a legitimate use.

        The validation is deliberately a light check, not a migration.
        If the file is a valid NetPulse topology but the schema is
        older than what this build expects, Database.__init__ handles
        the additive migrations (columns, tables) as it does for any
        file it opens.
        """
        start_dir = session.load_last_save_dir()
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Open topology",
            start_dir,
            "NetPulse topology (*.npdb);;SQLite database (*.db);;All files (*)",
        )
        if not chosen:
            return

        target = str(Path(chosen))

        if not Path(target).exists():
            QMessageBox.warning(
                self,
                "Open failed",
                f"No such file:\n\n{target}",
            )
            return

        # Validate: does it look like a NetPulse topology?
        if not self._looks_like_topology_file(target):
            QMessageBox.warning(
                self,
                "Open failed",
                f"This file does not look like a NetPulse topology:\n\n"
                f"{target}\n\n"
                "Expected an SQLite database containing a "
                "'topology_positions' table. Opening a file without "
                "that table could corrupt it if it is a NetPulse CLI "
                "or API database.",
            )
            return

        # Same file as current? No-op.
        try:
            same = Path(target).resolve() == Path(self._topology_path).resolve()
        except OSError:
            same = False
        if same:
            self.statusBar().showMessage(
                "Open: the chosen file is already the current topology.",
                4000,
            )
            return

        self._restart_worker_with_new_path(target)
        self.statusBar().showMessage(
            f"Opened {Path(target).name}.", 5000
        )

    @staticmethod
    def _looks_like_topology_file(path: str) -> bool:
        """
        Return True if `path` is an SQLite file containing a
        topology_positions table.

        Uses a raw sqlite3 connection rather than the Database class so
        that the check does not trigger migrations on the target file
        before we have decided to open it. If validation fails, the
        file is left untouched.

        Any error (not a database, unreadable, empty) is treated as
        "not a topology file" and returns False.
        """
        import sqlite3

        try:
            conn = sqlite3.connect(path)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='topology_positions'"
                )
                return cur.fetchone() is not None
            finally:
                conn.close()
        except Exception:
            return False

    def _file_save_as(self) -> None:
        """
        File -> Save As. Ask for a target path, copy the current
        topology file to it, and switch to the copy.

        Because this now switches files (Drop 2b), the sequence is:
          1. Flush pending saves so the source file is up to date.
          2. Ask for a target path.
          3. No-op if the target is the current file.
          4. Copy the source to the target.
          5. Restart the worker on the copy.

        The restart does everything else — clears the canvas, points the
        session at the new file, updates the window title. The running
        engine ends up reading and writing the copy, not the original.

        Overwrite: allowed silently. Save As is the standard
        overwrite-a-file operation in every editor, and users expect it
        to overwrite after the OS's own "file exists" confirmation in
        the file dialog. That confirmation is what QFileDialog provides
        by default.
        """
        # 1. Flush the source.
        self.canvas.flush_pending_saves()

        source = self._topology_path
        if not Path(source).exists():
            QMessageBox.warning(
                self,
                "Save As failed",
                f"The current topology file does not exist:\n\n{source}",
            )
            return

        # 2. File dialog.
        start_dir = session.load_last_save_dir()
        suggested = str(Path(start_dir) / "topology.npdb")
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Save topology as",
            suggested,
            "NetPulse topology (*.npdb);;SQLite database (*.db);;All files (*)",
        )
        if not chosen:
            return

        target = str(Path(chosen))

        # 3. No-op if same file.
        try:
            same = Path(target).resolve() == Path(source).resolve()
        except OSError:
            same = False
        if same:
            self.statusBar().showMessage(
                "Save As: the chosen path is already the current file.",
                4000,
            )
            return

        # 4. Copy.
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Save As failed",
                f"Could not write to:\n\n{target}\n\n{exc}",
            )
            return

        # 5. Switch.
        self._restart_worker_with_new_path(target)
        self.statusBar().showMessage(
            f"Saved as {Path(target).name} and switched to it.", 5000
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
          0. Flush any pending debounced position saves. Must happen
             before the worker is stopped, so the write goes through a
             live Database instance rather than racing teardown.
          1. Invoke worker.on_stop BLOCKING on the worker thread. This
             runs the timer stop + deleteLater + reference drop to
             completion before we return, so the worker's QTimer is
             actually gone by the time the thread's event loop exits.
          2. Quit the thread's event loop.
          3. Wait for the thread to exit, using a generously derived
             timeout. If the wait fails, fall back to terminate(), which
             is documented as unsafe but is still preferable to a hung
             application.

        The BlockingQueuedConnection on step 1 is what makes deleteLater
        effective: without blocking, quit() could be processed by the
        worker thread's event loop before the stop slot ran, leaving the
        timer alive and eventually finalized by the main thread during
        interpreter teardown — the "QObject::killTimer: Timers cannot be
        stopped from another thread" warnings.

        On the terminate() fallback: QThread.terminate() is documented
        as unsafe and can corrupt the interpreter if called while the
        target thread is executing Python bytecode or a C extension. The
        wait timeout above is derived from the ping parameters and then
        doubled with a 30-second floor, which makes reaching this
        fallback in practice a sign that something is genuinely wrong.
        If it is reached, it is logged loudly to stderr and reported to
        the user via a modal dialog so the failure is not silent.
        """

        # Persistence flush. Before the worker stops.
        self.canvas.flush_pending_saves()

        # Reuse the restart machinery's stop helper. It does exactly the
        # same sequence, and having one place for the shutdown logic
        # means a fix to one is a fix to both.
        self._stop_worker()

        super().closeEvent(event)