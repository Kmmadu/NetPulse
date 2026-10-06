"""
Header bar — top strip of the main window.

Contents, left to right:
    "NetPulse"   — the app's wordmark.
    (stretch)    — pushes the rest to the right.
    "Settings"   — opens the SMTP configuration dialog.
    "Zoom 100 %" — opens a dropdown of zoom presets and the Fit action.

The header bar is fixed-height. It sits above the canvas in MainWindow's
layout. It does not overlay the canvas — the canvas gets the remaining
space below. The zoom dropdown, by contrast, IS an overlay: it appears
over the canvas when the Zoom button is clicked, and closes on selection
or click-outside.

Signals:
    settingsRequested()   — user clicked Settings.
    zoomRequested(float)  — user picked a numeric preset from the dropdown.
    fitRequested()        — user picked the "Fit" action from the dropdown.

The Zoom button's label is updated by `set_current_zoom`, which
MainWindow wires to the canvas's `zoomChanged` signal.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
)


class HeaderBar(QFrame):
    """Fixed-height header strip. One place for global controls."""

    # Signals, matching the old ZoomPanel's contract so MainWindow
    # wiring is unchanged for the zoom-related connections.
    settingsRequested = Signal()
    zoomRequested = Signal(float)
    fitRequested = Signal()

    HEADER_HEIGHT = 40

    # Preset percentages, in ascending order. "Fit" is an action, handled
    # separately, and appears at the top of the dropdown.
    PRESETS = (25, 50, 75, 100, 150, 200, 300, 400)

    _FIT_LABEL = "Fit"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(self.HEADER_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # Border only on the bottom edge, so the header reads as a strip
        # rather than a floating box. The colour is a very light grey
        # that works on both the light and (future) dark canvas theme.
        self.setStyleSheet(
            "HeaderBar {"
            "  background: #f8f9fa;"
            "  border-bottom: 1px solid #e8eaed;"
            "}"
        )

        # Wordmark
        wordmark = QLabel("NetPulse")
        wordmark.setStyleSheet(
            "color: #202124; font-size: 14px; font-weight: 600;"
            "padding: 0 12px;"
        )

        # Settings button
        self._settings_button = QPushButton("Settings")
        self._settings_button.setFlat(True)
        self._settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_button.setStyleSheet(self._flat_button_stylesheet())
        self._settings_button.clicked.connect(self.settingsRequested.emit)

        # Zoom button. Its text is updated live by set_current_zoom.
        self._zoom_button = QPushButton("Zoom 100 %")
        self._zoom_button.setFlat(True)
        self._zoom_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._zoom_button.setStyleSheet(self._flat_button_stylesheet())
        self._zoom_button.clicked.connect(self._open_zoom_menu)

        # The zoom dropdown is a QMenu, created lazily on first open.
        # QMenu is the standard Qt mechanism for a floating list of
        # actions that closes on selection or click-outside; using it
        # here means we do not need a custom popup widget.
        self._zoom_menu: QMenu | None = None

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 8, 0)
        layout.setSpacing(4)
        layout.addWidget(wordmark)
        layout.addStretch(1)
        layout.addWidget(self._settings_button)
        layout.addWidget(self._zoom_button)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_current_zoom(self, scale: float) -> None:
        """
        Update the Zoom button's label to reflect the current zoom.
        Called by MainWindow when the canvas reports a zoom change,
        including changes initiated by Ctrl+wheel or Ctrl+0.

        `scale` is a float where 1.0 == 100%. The percentage is rounded
        to the nearest integer. Any value can be shown, not just the
        presets — this was the reason we moved from a button column to a
        dynamic label in the first place.
        """
        pct = int(round(scale * 100))
        self._zoom_button.setText(f"Zoom {pct} %")

    # ------------------------------------------------------------------
    # Internal — zoom menu
    # ------------------------------------------------------------------

    def _open_zoom_menu(self) -> None:
        """
        Build (if needed) and pop up the zoom menu below the Zoom button.
        QMenu.popup positions itself; we pass the button's bottom-left
        corner so the menu opens directly under the button and does not
        cover it.
        """
        if self._zoom_menu is None:
            self._zoom_menu = QMenu(self)

            # Fit at the top, as an action.
            fit_action = QAction(self._FIT_LABEL, self._zoom_menu)
            fit_action.triggered.connect(self.fitRequested.emit)
            self._zoom_menu.addAction(fit_action)

            self._zoom_menu.addSeparator()

            # Numeric presets.
            for pct in self.PRESETS:
                act = QAction(f"{pct} %", self._zoom_menu)
                # Bind the percentage into the lambda's default args so
                # each action captures its own value rather than the last
                # one from the loop.
                act.triggered.connect(
                    lambda _checked=False, p=pct: self.zoomRequested.emit(p / 100.0)
                )
                self._zoom_menu.addAction(act)

        # Position the menu under the button.
        bottom_left = self._zoom_button.mapToGlobal(
            self._zoom_button.rect().bottomLeft()
        )
        self._zoom_menu.popup(bottom_left)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    @staticmethod
    def _flat_button_stylesheet() -> str:
        """
        Flat buttons for the header. Light theme; will be revised when we
        take the canvas dark in Milestone 7.96. The palette here is the
        one already in use elsewhere (accent hover #f1f3f4, text #202124)
        so the header does not introduce a new colour language.
        """
        return (
            "QPushButton {"
            "  padding: 4px 10px;"
            "  border: none;"
            "  border-radius: 4px;"
            "  background: transparent;"
            "  color: #202124;"
            "}"
            "QPushButton:hover {"
            "  background: #f1f3f4;"
            "}"
            "QPushButton:pressed {"
            "  background: #e8eaed;"
            "}"
        )