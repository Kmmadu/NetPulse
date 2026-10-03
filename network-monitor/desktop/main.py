#!/usr/bin/env python3
"""
NetPulse desktop GUI — entry point.

Milestone 6: adds sys.path setup so the desktop app can import from the
sibling `app/` package, suppresses a noisy Wayland text-input diagnostic,
and keeps a Python reference to the MainWindow so it is not garbage
collected while the Qt event loop runs.
"""

import os
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NetPulse")
    app.setOrganizationName("NetPulse")

    window = MainWindow()
    window.show()

    # `window` must be kept alive for the duration of the event loop.
    # Assigning to a local would allow Python to garbage-collect it as
    # soon as main() returns, which never happens while app.exec() runs,
    # but keeping an explicit attribute is the standard Qt convention.
    app._netpulse_main_window = window

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())