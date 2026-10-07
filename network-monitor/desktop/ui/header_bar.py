"""
Header bar — top strip of the main window.

Contents, left to right:
    [logo]       — a 20x20 tinted SVG pulse mark.
    "NetPulse"   — the wordmark, two-tone: "Net" in dark grey, "Pulse"
                   in the accent blue (#6B9BFF).
    "Topology"   — a muted section label (#9AA0A6), the current view name.
    (stretch)    — pushes the rest to the right.
    [find]       — a small magnifier button opening the find bar.
    "Settings"   — opens the SMTP configuration dialog.
    "Zoom 100 %" — opens a dropdown of zoom presets and the Fit action.

The header bar is fixed-height. It sits above the canvas in MainWindow's
layout. It does not overlay the canvas — the canvas gets the remaining
space below. The zoom dropdown IS an overlay: it appears over the canvas
when the Zoom button is clicked, and closes on selection or click-outside.

Signals:
    settingsRequested()   — user clicked Settings.
    zoomRequested(float)  — user picked a numeric preset from the dropdown.
    fitRequested()        — user picked the "Fit" action from the dropdown.
    findRequested()       — user clicked the find button (or pressed Ctrl+F,
                            which is wired in MainWindow to the same slot).

The Zoom button's label is updated by `set_current_zoom`, which
MainWindow wires to the canvas's `zoomChanged` signal.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
)

from ui.device_icons import icon_pixmap_by_name


class HeaderBar(QFrame):
    """Fixed-height header strip. One place for global controls."""

    # Signals, matching the old ZoomPanel's contract so MainWindow
    # wiring is unchanged for the zoom-related connections.
    settingsRequested = Signal()
    zoomRequested = Signal(float)
    fitRequested = Signal()
    findRequested = Signal()

    HEADER_HEIGHT = 40

    # Wordmark colours. The header background is pale (#f8f9fa), so the
    # neutral half of the wordmark must be dark, not near-white. The
    # value here deliberately differs from the node name colour
    # (#E8EAED) used in device_node.py — that colour is chosen for the
    # dark node cards and would be invisible on the header. "Pulse"
    # stays on the accent blue that matches the selected-edge colour
    # and the logo tint.
    WORDMARK_COLOR_NEUTRAL = "#202124"
    WORDMARK_COLOR_ACCENT = "#6B9BFF"

    # Section label. Muted grey, deliberately less prominent than the
    # wordmark. Same grey as the node IP tooltip colour, so the two
    # "secondary text" uses share one value.
    SECTION_LABEL_COLOR = "#9AA0A6"

    # Logo appearance. The icon is drawn at 20x20; the SVG source is a
    # 24x24 viewBox and the loader scales it down. The tint is the accent
    # blue at full opacity so the mark reads as a distinct brand element,
    # not just another monochrome glyph.
    LOGO_SIZE = 20
    LOGO_TINT = QColor("#6B9BFF")

    # Find icon appearance. 16x16 to match the visual weight of the
    # other header icons; tinted dark like the header text so it does
    # not compete with the accent-blue logo.
    FIND_ICON_SIZE = 16
    FIND_ICON_TINT = QColor("#5f6368")

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

        # --- Logo -----------------------------------------------------
        # Loaded through the same SVG pipeline as the device icons and
        # the (now removed) tool icons: render at LOGO_SIZE, tint with
        # LOGO_TINT. A missing logo.svg would return a transparent
        # pixmap and the header would render without a logo — degraded
        # but not broken.
        logo_pixmap = icon_pixmap_by_name(
            "logo.svg", self.LOGO_TINT, self.LOGO_SIZE
        )
        logo_label = QLabel()
        logo_label.setPixmap(logo_pixmap)
        logo_label.setFixedSize(self.LOGO_SIZE, self.LOGO_SIZE)
        logo_label.setStyleSheet("padding: 0; margin: 0;")

        # --- Wordmark -------------------------------------------------
        # Two-tone split, rendered as rich text in a single QLabel.
        # Qt's QLabel consumes a limited HTML subset; the span/colour
        # usage here is within it. Semibold retained from the previous
        # version so the wordmark's weight is unchanged.
        wordmark = QLabel(
            f'<span style="color:{self.WORDMARK_COLOR_NEUTRAL}">Net</span>'
            f'<span style="color:{self.WORDMARK_COLOR_ACCENT}">Pulse</span>'
        )
        wordmark.setTextFormat(Qt.TextFormat.RichText)
        wordmark.setStyleSheet(
            "font-size: 14px; font-weight: 600; padding: 0; margin: 0;"
        )

        # --- Section label --------------------------------------------
        # The current view name. Muted grey, smaller than the wordmark.
        # This is a label, not a control — it has no click handler, no
        # hover state. When future milestones add other views, this text
        # changes; no other change is needed here.
        section_label = QLabel("Topology")
        section_label.setStyleSheet(
            f"color: {self.SECTION_LABEL_COLOR};"
            " font-size: 12px;"
            " padding: 0; margin: 0;"
        )

        # --- Find button ----------------------------------------------
        # Opens the find bar. The button emits a signal; MainWindow
        # handles opening the bar. This keeps the header free of any
        # knowledge of the bar's internals.
        self._find_button = QPushButton()
        self._find_button.setIcon(
            QIcon(
                icon_pixmap_by_name(
                    "find.svg", self.FIND_ICON_TINT, self.FIND_ICON_SIZE
                )
            )
        )
        self._find_button.setIconSize(
            QSize(self.FIND_ICON_SIZE, self.FIND_ICON_SIZE)
        )
        self._find_button.setFixedSize(28, 28)
        self._find_button.setToolTip("Find device by name (Ctrl+F)")
        self._find_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._find_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._find_button.setStyleSheet(self._flat_button_stylesheet())
        self._find_button.clicked.connect(self.findRequested.emit)

        # --- Settings button ------------------------------------------
        self._settings_button = QPushButton("Settings")
        self._settings_button.setFlat(True)
        self._settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_button.setStyleSheet(self._flat_button_stylesheet())
        self._settings_button.clicked.connect(self.settingsRequested.emit)

        # --- Zoom button ----------------------------------------------
        self._zoom_button = QPushButton("Zoom 100 %")
        self._zoom_button.setFlat(True)
        self._zoom_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._zoom_button.setStyleSheet(self._flat_button_stylesheet())
        self._zoom_button.clicked.connect(self._open_zoom_menu)

        # The zoom dropdown is a QMenu, created lazily on first open.
        self._zoom_menu: QMenu | None = None

        # --- Layout ---------------------------------------------------
        # Left block:  [logo]  [NetPulse]  [Topology]  --- stretch ---
        # Right block:                     [find]  [Settings]  [Zoom ▼]
        #
        # Spacing chosen so the logo and wordmark are visually one unit
        # (small gap), while the section label sits apart (larger gap),
        # and the right-hand buttons use the same small inter-button
        # spacing as the previous version.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        layout.addWidget(logo_label)
        layout.addSpacing(2)          # small gap: logo → wordmark
        layout.addWidget(wordmark)
        layout.addSpacing(14)         # larger gap: wordmark → section
        layout.addWidget(section_label)

        layout.addStretch(1)

        layout.addWidget(self._find_button)
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
        Flat buttons for the header. Light theme; the palette is the one
        already in use elsewhere (accent hover #f1f3f4, text #202124) so
        the header does not introduce a new colour language.
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