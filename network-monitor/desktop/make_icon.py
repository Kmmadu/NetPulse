"""
Generate resources/netpulse.png — the app icon.

Draws a simple placeholder: a dark canvas-background square, an accent-
blue ring, and a bold "N" centred inside. Same palette as the header
logo (#6B9BFF ring, #0F1117 background), so the icon matches the app's
visual language.

Replace with a designed icon later; the installer only needs the file
to exist at resources/netpulse.png with a 256x256 size.

Run: python3 make_icon.py
"""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 — needed for QImage

    size = 256
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("#0F1117"))

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Accent-blue ring. Stroke width set via QPen.
    from PySide6.QtGui import QPen
    pen = QPen(QColor("#6B9BFF"))
    pen.setWidth(12)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(40, 40, size - 80, size - 80)

    # Bold "N".
    painter.setPen(QPen(QColor("#E8EAED")))
    font = QFont()
    font.setPointSize(96)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "N")

    painter.end()

    out_dir = os.path.join(os.path.dirname(__file__), "resources")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "netpulse.png")

    if not img.save(out_path):
        print(f"Failed to write {out_path}", file=sys.stderr)
        return 1

    print(f"Created {out_path} ({os.path.getsize(out_path)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())