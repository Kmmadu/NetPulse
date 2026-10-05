"""
SMTP configuration dialog.

Lets the user enter SMTP credentials, test the connection without leaving
the dialog, and save the values to desktop/.env. On save, the values are
also applied to the running process so alerting works without a restart.

The Test Connection button runs on a QThreadPool worker, not the GUI
thread: a blocking SMTP call would freeze the window for the duration of
the network round trip. The dialog reports the result via a signal
emitted from the worker.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
)

from ui import config_manager


class _TestSignals(QObject):
    """
    Signals for the background Test Connection worker. QRunnable is not
    itself a QObject, so it cannot declare signals; this wrapper provides
    them.
    """
    finished = Signal(bool, str)   # success, message


class _TestWorker(QRunnable):
    """
    Runs AlertServiceV2's connection test with the dialog's current values
    temporarily placed into os.environ, on a thread-pool thread.

    The result is reported by emitting `signals.finished(success, message)`.
    It never raises; SMTP errors are caught and reported as a failure with
    the exception text.

    Note: we deliberately construct a throwaway AlertServiceV2 rather than
    call _check_enabled() directly. Construction is the operation the app
    will actually perform when an alert fires, so testing it here tests the
    same code path the app uses. Its `_enabled` attribute tells us whether
    the credentials are good.
    """

    def __init__(self, values: dict):
        super().__init__()
        self.values = values
        self.signals = _TestSignals()

    @Slot()
    def run(self) -> None:
        # Save the current environment so we can restore it after the test.
        # Otherwise a failed test would leave the process configured with
        # bad credentials.
        import os
        import io
        from contextlib import redirect_stdout, redirect_stderr

        original = {k: os.environ.get(k) for k in self.values.keys()}
        try:
            for key, value in self.values.items():
                if value == "":
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

            from app.services.alert_v2 import AlertServiceV2

            # Capture both stdout and stderr so the SMTP conversation does
            # not spam the terminal for a dialog-internal test.
            #
            # AlertServiceV2's banner goes to stdout. Its SMTP conversation
            # uses smtplib's set_debuglevel(1), which writes to stderr.
            # Capturing only stdout (as an earlier version did) let the
            # SMTP trace reach the terminal despite the intent to suppress
            # it.
            out_buffer = io.StringIO()
            err_buffer = io.StringIO()
            try:
                with redirect_stdout(out_buffer), redirect_stderr(err_buffer):
                    service = AlertServiceV2()
            except Exception as exc:
                self.signals.finished.emit(
                    False, f"Unexpected error: {type(exc).__name__}: {exc}"
                )
                return

            if getattr(service, "_enabled", False):
                recipients = ", ".join(service.to_addrs)
                self.signals.finished.emit(
                    True, f"Connection successful. Alerts will go to {recipients}."
                )
            else:
                self.signals.finished.emit(
                    False,
                    "Connection test failed. Check server, port, username, "
                    "and password. See terminal output for details.",
                )
        finally:
            # Restore the environment.
            for key, original_value in original.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value


class ConfigDialog(QDialog):
    """
    The SMTP configuration dialog. Read the values back via `values` after
    the dialog returns QDialog.DialogCode.Accepted.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SMTP Configuration")
        self.setModal(True)
        self.setMinimumWidth(480)

        # ---- Fields ------------------------------------------------------
        current = config_manager.read_env()

        self._fields: dict[str, QLineEdit] = {}

        def _make_line_edit(key: str, placeholder: str = "") -> QLineEdit:
            edit = QLineEdit(current.get(key, ""))
            edit.setPlaceholderText(placeholder)
            self._fields[key] = edit
            return edit

        # SMTP fields. Password is masked.
        server_edit = _make_line_edit("SMTP_SERVER", "smtp.gmail.com")
        port_edit = _make_line_edit("SMTP_PORT", "587")
        username_edit = _make_line_edit("SMTP_USERNAME", "you@gmail.com")
        password_edit = _make_line_edit("SMTP_PASSWORD", "16-char App Password")
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        from_edit = _make_line_edit("SMTP_FROM", "you@gmail.com")
        to_edit = _make_line_edit("SMTP_TO", "you@gmail.com or a,b@c.d")

        # Cooldown fields. These are less commonly edited, but they belong
        # with the rest of the alert configuration.
        down_edit = _make_line_edit("ALERT_DOWN_COOLDOWN", "5")
        recovery_edit = _make_line_edit("ALERT_RECOVERY_COOLDOWN", "5")
        erratic_edit = _make_line_edit("ALERT_ERRATIC_COOLDOWN", "30")
        flapping_edit = _make_line_edit("ALERT_FLAPPING_SUPPRESSION", "60")

        # ---- Layout ------------------------------------------------------
        form = QFormLayout()
        form.addRow("SMTP server", server_edit)
        form.addRow("SMTP port", port_edit)
        form.addRow("SMTP username", username_edit)
        form.addRow("SMTP password", password_edit)
        form.addRow("From address", from_edit)
        form.addRow("To address(es)", to_edit)
        form.addRow("Down cooldown (min)", down_edit)
        form.addRow("Recovery cooldown (min)", recovery_edit)
        form.addRow("Erratic cooldown (min)", erratic_edit)
        form.addRow("Flapping suppression (min)", flapping_edit)

        # ---- Disclosure --------------------------------------------------
        disclosure = QLabel(
            "Credentials are stored in plaintext at\n"
            f"{config_manager.ENV_PATH}\n"
            "and are not committed to version control."
        )
        disclosure.setWordWrap(True)
        disclosure.setStyleSheet("color: #5f6368; font-size: 11px;")

        # ---- Test button and status -------------------------------------
        self._test_button = QPushButton("Test Connection")
        self._test_button.clicked.connect(self._on_test_clicked)

        self._test_status = QLabel("")
        self._test_status.setStyleSheet("color: #5f6368; font-size: 11px;")

        test_row = QHBoxLayout()
        test_row.addWidget(self._test_button)
        test_row.addWidget(self._test_status)
        test_row.addStretch(1)

        # ---- OK / Cancel -------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(disclosure)
        layout.addLayout(test_row)
        layout.addWidget(buttons)

        # Non-blocking guard against double-clicks on the test button.
        self._test_in_flight = False

    # ------------------------------------------------------------------
    # Test Connection
    # ------------------------------------------------------------------

    def _collect_values(self) -> dict:
        return {key: edit.text().strip() for key, edit in self._fields.items()}

    def _on_test_clicked(self) -> None:
        if self._test_in_flight:
            return
        self._test_in_flight = True
        self._test_button.setEnabled(False)
        self._test_status.setText("Testing…")
        self._test_status.setStyleSheet("color: #5f6368; font-size: 11px;")

        values = self._collect_values()
        worker = _TestWorker(values)
        worker.signals.finished.connect(self._on_test_finished)
        QThreadPool.globalInstance().start(worker)

    @Slot(bool, str)
    def _on_test_finished(self, success: bool, message: str) -> None:
        self._test_in_flight = False
        self._test_button.setEnabled(True)
        if success:
            self._test_status.setStyleSheet("color: #34a853; font-size: 11px;")
        else:
            self._test_status.setStyleSheet("color: #ea4335; font-size: 11px;")
        self._test_status.setText(message)

    # ------------------------------------------------------------------
    # Result accessors
    # ------------------------------------------------------------------

    @property
    def values(self) -> dict:
        return self._collect_values()