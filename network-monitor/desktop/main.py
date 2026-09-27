#!/usr/bin/env python3
"""
NetPulse desktop GUI — entry point.

Milestone 1: launches the PySide6 application shell.
No monitoring, no database, no alerts yet.
"""

import sys
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NetPulse")
    app.setOrganizationName("NetPulse")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())