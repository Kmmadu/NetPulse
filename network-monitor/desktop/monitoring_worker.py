"""
Monitoring worker — runs NetPulse's MonitoringEngine on a background thread.

Design:
  - A MonitoringWorker is created on the GUI thread, then moveToThread()'d
    onto a QThread. Every method of this class therefore runs on the worker
    thread, provided callers use queued connections or QMetaObject.invokeMethod
    with Qt.QueuedConnection / BlockingQueuedConnection. Do NOT call its
    methods directly from the GUI thread; use the signals and the
    blocking-invoke pattern declared below.
  - The worker owns a MonitoringEngine constructed with its own database
    file (desktop/data/desktop_monitor.db). It does NOT share the CLI's
    database, by design. That file is deleted at the start of every session
    so it acts as a per-session scratch file: MonitoringEngine.check_single_device
    writes devices into the `devices` table via Database._ensure_devices_synced()
    on first ping, and without a reset the file accumulates a permanent
    record of every device ever pinged — including ones not present on the
    current canvas. Milestone 8 will replace this with real persistence
    driven by the canvas.
  - The worker does NOT call monitor_forever(). That loop has no
    cooperative shutdown path and would need QThread.terminate() to stop.
    Instead, a QTimer fires every INTERVAL_SECONDS on the worker thread
    and calls engine.check_all_devices(), which runs the full pipeline
    (parallel ping, process_check, alert handling, DB writes) and returns
    a list of result dicts. The list is emitted as one cycleComplete signal.
  - Registration and unregistration of devices are queued signals. That
    means the worker thread's event loop serialises them against the
    QTimer's timeout slot, so the device dict is never mutated while
    check_all_devices() is iterating it. No mutex is needed or wanted;
    a mutex would not help because check_all_devices() iterates the dict
    without holding a lock of its own.
  - When a device is registered and the engine is already running, an
    immediate single-device check is performed for that device only, and
    its result is emitted as a one-element cycleComplete. This gives a
    newly-created node a status within ~2 seconds instead of waiting up
    to one full cycle. See on_register_node().
  - Re-registration of an existing device_id updates the Device in place
    rather than constructing a new one. This preserves the state machine's
    memory (status, fail count, down_since, sample windows) across edits
    like an IP change, which is what allows a recovery alert to fire when
    a device that was DOWN is corrected to a reachable address. See
    _inject_device().

Timer timing note (important):
    QThread.started is emitted from the newly started thread *before* the
    thread enters its event loop. A QTimer created and started inside a
    slot connected to that signal has no running event loop to fire into
    and will silently never tick. The fix is to defer timer creation via
    QTimer.singleShot(0, ...), which runs on the next event-loop turn,
    by which point the loop is definitely live.

Shutdown:
    on_stop() sets a stop-requested flag, stops the timer, schedules it
    for deletion via deleteLater(), and drops the Python reference. It is
    invoked from the GUI thread as a *blocking* cross-thread call
    (BlockingQueuedConnection) so it runs to completion on the worker
    thread before thread.quit() is called. That ordering is what makes
    the deleteLater() actually take effect: without blocking, quit()
    could be processed by the worker thread's event loop before the stop
    slot ran, leaving the timer alive and eventually finalized by the
    main thread during interpreter teardown — which is what produces the
    "QObject::killTimer: Timers cannot be stopped from another thread"
    warnings on exit.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

# Make `app` importable when this module is imported from the desktop app.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.models.device import Device, DeviceStatus  # noqa: E402
from app.core.monitor_engine import MonitoringEngine  # noqa: E402


# Where the desktop app keeps its own monitoring database. Relative to
# desktop/ because the desktop app is launched from there. Created
# automatically by Database.__init__ on first use, and DELETED at the
# start of every session (see _reset_desktop_db) so it acts as a
# per-session scratch file until Milestone 8 introduces real persistence.
_DB_PATH = str(Path(__file__).resolve().parent / "data" / "desktop_monitor.db")

# How often the worker runs a full check cycle. 5 seconds: fast enough that
# a newly added node turns green on the second cycle within ~10 seconds of
# creation (the first cycle produces a "pending" sample due to the engine's
# stability check; the second commits the transition). The immediate check
# in on_register_node supplies the first sample, so the wait for the
# committed state is one INTERVAL_SECONDS.
INTERVAL_SECONDS = 5

# Per-device ping parameters the worker injects into each Device. Exported
# so main_window.py can derive its shutdown wait timeout from the same
# numbers the worker actually uses, rather than from a hard-coded guess.
#
# A full cycle issues PING_COUNT ICMP packets per device (parallel across
# devices), each with a PING_TIMEOUT upper bound, and the engine retries
# up to RETRY_COUNT times before declaring DOWN.
PING_COUNT = 3          # matches MonitoringEngine.ping(count=3) default
PING_TIMEOUT = 2        # matches Device(timeout=2) below
RETRY_COUNT = 2         # matches Device(retry_count=2) below


def _reset_desktop_db() -> None:
    """
    Delete the desktop app's monitoring database, if it exists, so the
    current session starts with an empty devices table.

    Rationale: MonitoringEngine.check_single_device() writes a device row
    into the `devices` table the first time it pings that device, via
    Database._ensure_devices_synced(). Without a reset, every session
    accumulates rows for devices that were pinged once and never seen
    again — including ones never created in the current session — and the
    engine's initial-state check pings all of them. That both slows
    startup and fills the terminal with cycles for invisible devices.

    Deleting the file (rather than deleting rows within it) also removes
    the -wal and -shm sidecar files cleanly, and is one operation instead
    of three.

    Milestone 8 replaces this: the desktop app will persist topology
    deliberately, and the DB will be the source of truth the canvas loads
    from. Until then, the desktop DB is a per-session scratch file.
    """
    db_path = Path(_DB_PATH)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            try:
                os.remove(p)
            except OSError as exc:
                # Non-fatal: worst case the engine appends to an existing
                # DB this session. Report and continue.
                print(
                    f"[worker] could not remove {p}: {exc!r}",
                    file=sys.stderr,
                )


class MonitoringWorker(QObject):
    """
    Runs a MonitoringEngine on a background thread and emits cycle results.

    Public interface (all invoked from the GUI thread, dispatched to the
    worker thread via queued connections, except where noted):

        engineReady       -> emitted once, after the engine is constructed
                             and the timer is running.
        cycleComplete     -> emitted once per check cycle, carrying a list
                             of result dicts (one per device). Also emitted
                             once with a single-element list after a newly
                             registered device's immediate first check.
        registerNode      -> signal; adds a Device to the engine.
        unregisterNode    -> signal; removes a Device from the engine.
        stop              -> signal; retained for API compatibility. The
                             canvas and MainWindow do not emit it directly;
                             MainWindow invokes on_stop() as a
                             BlockingQueuedConnection instead, so that
                             shutdown is deterministic. Kept here in case
                             a future caller wants a non-blocking stop.

    Every method of this class except __init__ runs on the worker thread.
    Do not touch self._engine, self._timer, or self._pending_registrations
    from the GUI thread.
    """

    engineReady = Signal()
    cycleComplete = Signal(list)

    registerNode = Signal(str, str, str)   # device_id, name, ip_address
    unregisterNode = Signal(str)           # device_id
    stop = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._engine: Optional[MonitoringEngine] = None
        self._timer: Optional[QTimer] = None
        # Set by on_stop(). Checked by _on_tick() before starting a cycle.
        # See module docstring, "Shutdown", for why this can only prevent
        # the *next* cycle and cannot interrupt one in progress.
        self._stop_requested: bool = False
        # Registrations that arrived before the engine existed. Applied
        # once on_thread_started runs. Order preserved because it is a
        # list, not a set.
        self._pending_registrations: List[tuple] = []

    # ------------------------------------------------------------------
    # Lifecycle — runs on the worker thread
    # ------------------------------------------------------------------

    @Slot()
    def on_thread_started(self) -> None:
        """
        Reset the per-session DB, construct the engine, and schedule the
        timer. Connected to the QThread's started signal (queued
        connection). Runs on the worker thread the moment the thread
        enters its event loop.

        The timer is not created here directly. QThread.started is emitted
        before the thread's event loop is running, and a QTimer started at
        that moment never fires. QTimer.singleShot(0, ...) defers the
        creation to the next event-loop turn, by which point the loop is
        definitely live.
        """
        _reset_desktop_db()

        self._engine = MonitoringEngine(db_path=_DB_PATH)
        self._engine.devices.clear()

        for device_id, name, ip_address in self._pending_registrations:
            self._inject_device(device_id, name, ip_address)
        self._pending_registrations.clear()

        QTimer.singleShot(0, self._start_timer)
        self.engineReady.emit()

    @Slot()
    def _start_timer(self) -> None:
        """
        Create and start the cycle timer. Runs on the worker thread via
        the single-shot deferral in on_thread_started, at a point where
        the thread's event loop is definitely running.
        """
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_SECONDS * 1000)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    @Slot()
    def on_stop(self) -> None:
        """
        Handle a shutdown request. Stops the timer, schedules it for
        deletion on the worker thread, and drops the Python reference.
        Also sets the stop flag so no further cycle will start.

        Invoked from the GUI thread via BlockingQueuedConnection (see
        MainWindow.closeEvent), so this runs to completion on the worker
        thread *before* thread.quit() is called. That ordering is what
        makes deleteLater() effective: if quit() had already been
        enqueued and processed first, deleteLater() would be a no-op and
        the timer would survive into interpreter teardown, where it would
        be finalized on the main thread and Qt would emit the
        "QObject::killTimer: Timers cannot be stopped from another
        thread" warnings.

        Cannot interrupt a cycle already inside check_all_devices(); that
        cycle runs to completion before the event loop processes this
        slot. See module docstring, "Shutdown".
        """
        self._stop_requested = True
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

    # ------------------------------------------------------------------
    # Device registration — slots, run on the worker thread
    # ------------------------------------------------------------------

    @Slot(str, str, str)
    def on_register_node(self, device_id: str, name: str, ip_address: str) -> None:
        """
        Add a device to the engine. Queued from the GUI thread.

        If the engine is already up, an immediate single-device check is
        run for the newly added device so its status is populated within
        ~2 seconds rather than waiting up to one full INTERVAL_SECONDS
        cycle. The result is emitted as a one-element cycleComplete; the
        canvas slot handles a list of any length.

        Deliberately calls check_single_device() rather than
        check_all_devices(): the latter would re-check every existing
        device on every node addition, which is wasteful. Deliberately
        does not use is_initial_check=True: that flag is part of the
        engine's Device.process_check signature and touching it would
        mean modifying app/.
        """
        if self._engine is None:
            # Engine not up yet. Queue it; on_thread_started will apply.
            self._pending_registrations.append((device_id, name, ip_address))
            return

        self._inject_device(device_id, name, ip_address)

        device = self._engine.devices.get(device_id)
        if device is None:
            # _inject_device decided not to add it (already present).
            return

        try:
            result = self._engine.check_single_device(device)
        except Exception as exc:
            # Defensive: an immediate check failing must not take down the
            # worker thread. Report and move on; the timer cycle will
            # retry the device in INTERVAL_SECONDS.
            print(
                f"[worker] immediate check for {name} raised: {exc!r}",
                file=sys.stderr,
            )
            return

        self.cycleComplete.emit([result])

    @Slot(str)
    def on_unregister_node(self, device_id: str) -> None:
        """Remove a device from the engine. Queued from the GUI thread."""
        if self._engine is None:
            # Nothing to unregister if the engine is not up. Drop any
            # pending registration with this id.
            self._pending_registrations = [
                t for t in self._pending_registrations if t[0] != device_id
            ]
            return
        if device_id in self._engine.devices:
            del self._engine.devices[device_id]

    def _inject_device(self, device_id: str, name: str, ip_address: str) -> None:
        """
        Ensure a Device for the given id is present in the engine's dict,
        and update its mutable fields if it already exists.

        Behaviour:
          - If no Device with this id exists: build one and add it.
          - If one exists: update `name` and `ip_address` in place. Do NOT
            create a new Device and do NOT touch the state machine's
            fields (status, fail count, down_since, sample windows).

        Why update in place rather than replace: re-registration happens on
        every edit of name or IP (see canvas.edit_device). Constructing a
        new Device would reset its status to UNKNOWN and discard its
        history, so a device that was DOWN and whose IP has just been
        corrected would look like a fresh UNKNOWN device on the next check
        — and the recovery alert, which fires on `old_status == 'DOWN' and
        new_status != 'DOWN'`, would never be triggered. Updating the
        existing Device preserves the memory, so the transition is
        genuinely DOWN → UP and the recovery alert fires.

        Runs on the worker thread only.
        """
        existing = self._engine.devices.get(device_id)
        if existing is not None:
            existing.name = name
            existing.ip_address = ip_address
            return

        device = Device(
            device_id=device_id,
            name=name,
            ip_address=ip_address,
            retry_count=RETRY_COUNT,
            timeout=PING_TIMEOUT,
        )
        self._engine.devices[device_id] = device

    # ------------------------------------------------------------------
    # Cycle — runs on the worker thread
    # ------------------------------------------------------------------

    @Slot()
    def _on_tick(self) -> None:
        """
        One monitoring cycle. Runs on the worker thread; the GUI thread
        stays responsive because it is a different thread.

        check_all_devices() blocks for the duration of the cycle (parallel
        pings, ~3-5s for a handful of devices). That blocking is the point:
        the worker thread exists to absorb it.
        """
        if self._stop_requested:
            # Stop was requested between cycles. Do not start a new one.
            return
        if self._engine is None:
            return
        if not self._engine.devices:
            # Nothing to check. Still emit an empty list so the GUI can
            # clear statuses if it wants; harmless and keeps the contract.
            self.cycleComplete.emit([])
            return

        try:
            results = self._engine.check_all_devices()
        except Exception as exc:
            # Defensive: MonitoringEngine is well-behaved, but if anything
            # unexpected happens on the worker thread, we do not want the
            # thread to die silently.
            print(f"[worker] check_all_devices raised: {exc!r}", file=sys.stderr)
            return

        # Sort by name for stable GUI update order; the engine does not
        # guarantee order (ThreadPoolExecutor completion order).
        results.sort(key=lambda r: r.get("name", ""))
        self.cycleComplete.emit(results)