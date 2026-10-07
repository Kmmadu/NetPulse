"""
Find bar — floating search control for locating nodes by name.

Layout:

    ┌──────────────────────────────────────┐
    │  🔍  [input]   ▲  ▼  3 of 8   ✕     │
    └──────────────────────────────────────┘

Signals:
    queryChanged(str)     — fired on every keystroke in the input.
    nextRequested()       — user clicked ▼ or pressed Enter.
    previousRequested()   — user clicked ▲ or pressed Shift+Enter.
    closedRequested()     — user clicked ✕ or pressed Esc.

The bar does not know about the canvas. It emits the user's intent;
MainWindow wires the signals to the canvas's find API. This keeps the
bar a pure view.

Positioned by the canvas (parented to the canvas viewport) so that it
rides above the scene without being part of it. The bar consumes
keyboard focus while open; the canvas must not process its own key
handlers (Delete, Esc, etc.) while the bar is active. The canvas
checks the find bar's active state before running those handlers.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
)


class FindBar(QFrame):
    """
    Floating search bar. See module docstring for the layout and the
    signal contract.
    """

    queryChanged = Signal(str)
    nextRequested = Signal()
    previousRequested = Signal()
    closedRequested = Signal()

    BAR_WIDTH = 340

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedWidth(self.BAR_WIDTH)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.setStyleSheet(
            "FindBar {"
            "  background: rgba(26, 29, 36, 0.95);"
            "  border: 1px solid rgba(60, 66, 80, 0.8);"
            "  border-radius: 8px;"
            "}"
        )

        # --- Label (magnifier) ---------------------------------------
        # A small visual cue. Not interactive.
        magnifier = QLabel("🔍")
        magnifier.setStyleSheet(
            "color: #9AA0A6; font-size: 13px; padding: 0 2px;"
        )

        # --- Input ----------------------------------------------------
        self._input = QLineEdit()
        self._input.setPlaceholderText("Find device by name…")
        self._input.setStyleSheet(
            "QLineEdit {"
            "  background: rgba(15, 17, 23, 0.8);"
            "  color: #E8EAED;"
            "  border: 1px solid rgba(60, 66, 80, 0.6);"
            "  border-radius: 4px;"
            "  padding: 4px 8px;"
            "  font-size: 12px;"
            "}"
            "QLineEdit:focus {"
            "  border: 1px solid #6B9BFF;"
            "}"
        )
        self._input.textChanged.connect(self.queryChanged.emit)
        # Enter cycles forward; Shift+Enter cycles backward.
        self._input.returnPressed.connect(self._on_return_pressed)

        # --- Counter --------------------------------------------------
        self._counter = QLabel("")
        self._counter.setStyleSheet(
            "color: #9AA0A6; font-size: 11px; padding: 0 4px;"
        )
        self._counter.setMinimumWidth(52)
        self._counter.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- Nav buttons ---------------------------------------------
        self._prev_button = self._make_nav_button("▲", "Previous match (Shift+Enter)")
        self._prev_button.clicked.connect(self.previousRequested.emit)

        self._next_button = self._make_nav_button("▼", "Next match (Enter)")
        self._next_button.clicked.connect(self.nextRequested.emit)

        # --- Close button --------------------------------------------
        self._close_button = self._make_nav_button("✕", "Close (Esc)")
        self._close_button.clicked.connect(self.closedRequested.emit)

        # --- Layout ---------------------------------------------------
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        layout.addWidget(magnifier)
        layout.addWidget(self._input, 1)
        layout.addWidget(self._counter)
        layout.addWidget(self._prev_button)
        layout.addWidget(self._next_button)
        layout.addWidget(self._close_button)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_match_info(self, current: int, total: int) -> None:
        """
        Update the counter label. `current` is 1-indexed; `total` is the
        number of matches. Both zero means no matches.

        Cases:
            total = 0, current = 0 → "no matches" text
            total > 0, 1 ≤ current ≤ total → "N of M"
        """
        if total == 0:
            self._counter.setText("no matches")
        else:
            self._counter.setText(f"{current} of {total}")

    def focus_input(self) -> None:
        """
        Give keyboard focus to the input field. Called by the canvas
        when the bar is shown.
        """
        self._input.setFocus()
        self._input.selectAll()

    def query(self) -> str:
        """Return the current text in the input, unstripped."""
        return self._input.text()

    def clear(self) -> None:
        """Clear the input and counter. Called when the bar closes."""
        self._input.clear()
        self._counter.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_return_pressed(self) -> None:
        # Shift+Enter goes backward; Enter goes forward.
        # QLineEdit does not expose the modifier on returnPressed, so we
        # check the current keyboard modifier state at the moment of the
        # return press. This is the standard approach.
        from PySide6.QtWidgets import QApplication
        mods = QApplication.keyboardModifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self.previousRequested.emit()
        else:
            self.nextRequested.emit()

    def _make_nav_button(self, text: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(22, 22)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setStyleSheet(
            "QPushButton {"
            "  background: transparent;"
            "  color: #E8EAED;"
            "  border: none;"
            "  border-radius: 4px;"
            "  font-size: 11px;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(255, 255, 255, 0.08);"
            "}"
            "QPushButton:pressed {"
            "  background: rgba(255, 255, 255, 0.14);"
            "}"
        )
        return button

    def keyPressEvent(self, event) -> None:
        """
        Esc closes the bar. Handled at the bar level so the canvas does
        not have to also guard for it.
        """
        if event.key() == Qt.Key.Key_Escape:
            self.closedRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)