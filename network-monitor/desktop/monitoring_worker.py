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
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

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
    Do not touch self._engine, self._nodes, or self._timer from the GUI
    thread.
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
        # Guards against the (impossible in practice, but cheap to defend)
        # case of a register arriving before on_thread_started(). The
        # queued-connection ordering guarantees started() is delivered
        # before any queued slot, so this is belt-and-braces.
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
        that moment never fires. See module docstring.
        """
        print(f"[worker] constructing MonitoringEngine with db={_DB_PATH}")

        # Construct with our own DB path. This runs load_devices_from_db()
        # and _run_initial_state_check() against desktop/data/*.db, which
        # is empty on first run and contains only devices this app has
        # been told about on subsequent runs.
        self._engine = MonitoringEngine(db_path=_DB_PATH)

        # Discard whatever load_devices_from_db() produced. Even if the
        # file were non-empty, the GUI is the source of truth for which
        # devices exist in this session; devices are injected explicitly
        # via register_node.
        self._engine.devices.clear()

        # Apply any registrations that arrived before we were ready (see
        # note in __init__). Order preserved because _pending_registrations
        # is a list.
        for device_id, name, ip_address in self._pending_registrations:
            self._inject_device(device_id, name, ip_address)
        self._pending_registrations.clear()

        # Defer timer creation to the next event-loop iteration, when the
        # thread's event loop is guaranteed to be running.
        QTimer.singleShot(0, self._start_timer)

        print(f"[worker] engine ready, interval={INTERVAL_SECONDS}s")
        self.engineReady.emit()

    @Slot()
    def _start_timer(self) -> None:
        """
        Create and start the cycle timer. Runs on the worker thread via
        the single-shot deferral in on_thread_started, at a point where
        the thread's event loop is definitely running.
        """
        # DIAGNOSTIC — remove after Milestone 6 confirmed.
        print(
            f"[worker] _start_timer ENTRY on {QThread.currentThread()}, "
            f"self.thread()={self.thread()}",
            flush=True,
        )

        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_SECONDS * 1000)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()
        print(f"[worker] timer started, will tick every {INTERVAL_SECONDS}s")

    @Slot()
    def on_stop(self) -> None:
        """Stop the timer. Called from the GUI thread via queued signal
        before the thread is quit."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        print("[worker] stopped")

    # ------------------------------------------------------------------
    # Device registration — slots, run on the worker thread
    # ------------------------------------------------------------------

    @Slot(str, str, str)
    def on_register_node(self, device_id: str, name: str, ip_address: str) -> None:
        """Add a device to the engine. Queued from the GUI thread."""
        # DIAGNOSTIC — remove after Milestone 6 confirmed.
        print(f"[worker] on_register_node: {name} ({ip_address})", flush=True)

        if self._engine is None:
            # Engine not up yet. Queue it; on_thread_started will apply.
            self._pending_registrations.append((device_id, name, ip_address))
            return
        self._inject_device(device_id, name, ip_address)

    @Slot(str)
    def on_unregister_node(self, device_id: str) -> None:
        """Remove a device from the engine. Queued from the GUI thread."""
        # DIAGNOSTIC — remove after Milestone 6 confirmed.
        print(f"[worker] on_unregister_node: {device_id}", flush=True)

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

        The Device constructor accepts device_id, name, ip_address, and a
        handful of optional tuning parameters; the values here match what
        MonitoringEngine.load_devices_from_db() would produce for an entry
        in the devices table. The engine's check_single_device() reads
        device.timeout, device.retry_count, and the quality thresholds,
        all of which default to sensible values in the constructor.
        """
        # Skip if already present (re-registration is a no-op).
        if device_id in self._engine.devices:
            print(f"[worker] _inject_device: {name} already present, skipping", flush=True)
            return
        device = Device(
            device_id=device_id,
            name=name,
            ip_address=ip_address,
            retry_count=2,
            timeout=2,
        )
        self._engine.devices[device_id] = device
        # DIAGNOSTIC — remove after Milestone 6 confirmed.
        print(
            f"[worker] _inject_device: added {name} ({ip_address}); "
            f"engine.devices now has {len(self._engine.devices)} entries",
            flush=True,
        )

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
        # DIAGNOSTIC — remove after Milestone 6 confirmed.
        print(
            f"[worker] _on_tick ENTRY on {QThread.currentThread()}, "
            f"engine={'yes' if self._engine else 'no'}, "
            f"devices={len(self._engine.devices) if self._engine else 0}",
            flush=True,
        )

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