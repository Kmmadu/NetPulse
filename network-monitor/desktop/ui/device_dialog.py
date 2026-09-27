"""
Device properties dialog.

Fields: name, type, IP address, monitoring enabled. The IP field is
validated with Python's stdlib ipaddress.ip_address, which accepts both
IPv4 and IPv6 literals and rejects hostnames. OK is disabled while the
IP is invalid; the field's border turns red and a short message appears
below it to explain why.

OK / Cancel only. No modal error dialogs: all feedback is inline so the
dialog never stacks a second window on top of itself.
"""

from __future__ import annotations

import ipaddress
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QVBoxLayout,
    QLabel,
)

from ui.device_types import DeviceType


class DeviceDialog(QDialog):
    """
    Edit or create a device. Values are read back through the public
    attributes `name`, `ip_address`, `device_type`, and `monitoring_enabled`
    after exec() returns QDialog.DialogCode.Accepted.
    """

    INVALID_BORDER = "border: 1px solid #ea4335;"
    NORMAL_BORDER = ""

    def __init__(
        self,
        parent=None,
        *,
        title: str = "Device properties",
        name: str = "",
        ip_address: str = "",
        device_type: DeviceType = DeviceType.GENERIC,
        monitoring_enabled: bool = True,
    ):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)

        # --- Fields -------------------------------------------------
        self._name_edit = QLineEdit(name)
        self._name_edit.setPlaceholderText("e.g. core-router")

        self._type_combo = QComboBox()
        for dtype in DeviceType:
            # Store the enum member directly on the item, so we can read it
            # back without parsing the display string.
            self._type_combo.addItem(dtype.label, dtype)
        # Preselect the current type.
        index = self._type_combo.findData(device_type)
        if index >= 0:
            self._type_combo.setCurrentIndex(index)

        self._ip_edit = QLineEdit(ip_address)
        self._ip_edit.setPlaceholderText("e.g. 192.168.1.1 or fe80::1")
        self._ip_edit.textChanged.connect(self._on_ip_changed)

        self._ip_error_label = QLabel("")
        self._ip_error_label.setStyleSheet("color: #ea4335; font-size: 11px;")

        self._monitoring_check = QCheckBox("Monitoring enabled")
        self._monitoring_check.setChecked(monitoring_enabled)

        # --- Layout -------------------------------------------------
        form = QFormLayout()
        form.addRow("Name", self._name_edit)
        form.addRow("Type", self._type_combo)
        form.addRow("IP address", self._ip_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._ip_error_label)
        layout.addWidget(self._monitoring_check)
        layout.addWidget(buttons)

        # Seed the validation state so OK is correctly enabled/disabled on
        # first display (relevant when creating a new node with empty IP).
        self._on_ip_changed(self._ip_edit.text())

    # ------------------------------------------------------------------
    # IP validation
    # ------------------------------------------------------------------

    def _on_ip_changed(self, text: str) -> None:
        error = self._validate_ip(text)
        if error is None:
            self._ip_edit.setStyleSheet(self.NORMAL_BORDER)
            self._ip_error_label.setText("")
            self._ok_button.setEnabled(True)
        else:
            self._ip_edit.setStyleSheet(self.INVALID_BORDER)
            self._ip_error_label.setText(error)
            self._ok_button.setEnabled(False)

    @staticmethod
    def _validate_ip(text: str) -> Optional[str]:
        """
        Return None if `text` is a valid IP literal, else a short message.
        Empty string counts as invalid: a node without an IP cannot be
        monitored, and Milestone 5 is the last chance to require it before
        Milestone 6 wires the monitoring engine to it.
        """
        stripped = text.strip()
        if not stripped:
            return "IP address is required."
        try:
            ipaddress.ip_address(stripped)
        except ValueError:
            return "Not a valid IPv4 or IPv6 address (hostnames not accepted)."
        return None

    # ------------------------------------------------------------------
    # Result accessors
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name_edit.text().strip() or "device"

    @property
    def ip_address(self) -> str:
        return self._ip_edit.text().strip()

    @property
    def device_type(self) -> DeviceType:
        data = self._type_combo.currentData()
        # findData above guarantees this is a DeviceType, but be defensive.
        return data if isinstance(data, DeviceType) else DeviceType.GENERIC

    @property
    def monitoring_enabled(self) -> bool:
        return self._monitoring_check.isChecked()