#!/usr/bin/env python3
"""
NetPulse desktop GUI — entry point.

Milestone 6: sys.path setup for the sibling `app/` package, Wayland noise
suppression, explicit reference to the main window so it is not garbage
collected, and a SIGINT handler so Ctrl-C goes through the same clean
shutdown path as closing the window.
"""

import os
import signal
import sys
from pathlib import Path

# Suppress the chatty Wayland text-input diagnostic lines. Must be set
# before QApplication is constructed. Harmless on X11.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland.textinput=false")

# Make the sibling `app/` package importable. This file lives at
# network-monitor/desktop/main.py, so the repository root is one level up
# from this file's directory. We insert it at the *front* of sys.path so
# that `import app` resolves to the real NetPulse package and not to some
# unrelated module of the same name.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NetPulse")
    app.setOrganizationName("NetPulse")

    window = MainWindow()
    window.show()

    # Keep an explicit reference so the window is not garbage-collected
    # while the Qt event loop runs.
    app._netpulse_main_window = window

    # Route SIGINT through the normal Qt quit path. app.quit() exits the
    # event loop and (empirically) fires closeEvent on open windows, so
    # MainWindow's own shutdown logic runs.
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    # Qt does not wake its event loop for Python signal handlers on its
    # own. A periodic no-op timer gives the interpreter a chance to run
    # pending signal handlers every 200 ms. Without this, Ctrl-C is only
    # noticed the next time a Python callback runs, which can be never if
    # the app is idle.
    sigint_timer = QTimer()
    sigint_timer.start(200)
    sigint_timer.timeout.connect(lambda: None)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())