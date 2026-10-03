"""
Monitoring worker — runs NetPulse's MonitoringEngine on a background thread.

Design:
  - A MonitoringWorker is created on the GUI thread, then moveToThread()'d
    onto a QThread. Every method of this class therefore runs on the worker
    thread, provided callers use queued connections or QMetaObject.invokeMethod
    with Qt.QueuedConnection. Do NOT call its methods directly from the GUI
    thread; use the signals declared below.
  - The worker owns a MonitoringEngine constructed with its own database
    file (desktop/data/desktop_monitor.db). It does NOT share the CLI's
    database, by design: constructing MonitoringEngine runs
    load_devices_from_db() and an initial ping sweep, and we do not want
    the desktop app pinging (or alerting on) whatever devices the CLI
    might have configured.
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

Timer timing note (important):
    QThread.started is emitted from the newly started thread *before* the
    thread enters its event loop. A QTimer created and started inside a
    slot connected to that signal has no running event loop to fire into
    and will silently never tick. The fix is to defer timer creation via
    QTimer.singleShot(0, ...), which runs on the next event-loop turn,
    by which point the loop is definitely live.

Shutdown:
    on_stop() sets a stop-requested flag and stops the timer. Because the
    worker thread's event loop is blocked for the duration of any running
    check_all_devices() call, on_stop can only be delivered *between*
    cycles, never during one. The flag therefore guarantees that no new
    cycle starts after stop is requested; it cannot interrupt a cycle that
    is already in progress. The consequence is that shutdown always waits
    for at most one full cycle, and the wait timeout on the GUI side must
    be sized to cover that worst case. See main_window.py for the
    derivation.
"""

from __future__ import annotations

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
# automatically by Database.__init__ on first use.
_DB_PATH = str(Path(__file__).resolve().parent / "data" / "desktop_monitor.db")

# How often the worker runs a full check cycle.
INTERVAL_SECONDS = 10

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


class MonitoringWorker(QObject):
    """
    Runs a MonitoringEngine on a background thread and emits cycle results.

    Public interface (all invoked from the GUI thread, dispatched to the
    worker thread via queued connections):

        engineReady       -> emitted once, after the engine is constructed
                             and the timer is running.
        cycleComplete     -> emitted once per check cycle, carrying a list
                             of result dicts (one per device).
        registerNode      -> signal; adds a Device to the engine.
        unregisterNode    -> signal; removes a Device from the engine.
        stop              -> signal; stops the timer and prepares for
                             thread quit.

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
        Construct the engine and schedule the timer. Connected to the
        QThread's started signal (queued connection). Runs on the worker
        thread the moment the thread enters its event loop.

        The timer is not created here directly. QThread.started is emitted
        before the thread's event loop is running, and a QTimer started at
        that moment never fires. QTimer.singleShot(0, ...) defers the
        creation to the next event-loop turn, by which point the loop is
        definitely live.
        """
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
        Handle a shutdown request. Stops the timer and sets the stop flag
        so no further cycle will start. Called from the GUI thread via
        queued signal before the thread is quit.

        This cannot interrupt a cycle already inside check_all_devices();
        that cycle runs to completion before the event loop processes
        this slot. See module docstring, "Shutdown".
        """
        self._stop_requested = True
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    # ------------------------------------------------------------------
    # Device registration — slots, run on the worker thread
    # ------------------------------------------------------------------

    @Slot(str, str, str)
    def on_register_node(self, device_id: str, name: str, ip_address: str) -> None:
        """Add a device to the engine. Queued from the GUI thread."""
        if self._engine is None:
            # Engine not up yet. Queue it; on_thread_started will apply.
            self._pending_registrations.append((device_id, name, ip_address))
            return
        self._inject_device(device_id, name, ip_address)

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
        Build a Device and place it in the engine's dict. Runs on the
        worker thread only.

        The ping parameters (retry_count, timeout) are exported as module
        constants so main_window.py can derive its shutdown wait timeout
        from the same numbers the engine actually uses.
        """
        if device_id in self._engine.devices:
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