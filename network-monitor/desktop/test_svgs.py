"""One-off verification that the five SVG icons exist and parse under QtSvg."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).parent / "assets" / "icons"
EXPECTED = ["router.svg", "switch.svg", "server.svg", "pc.svg", "generic.svg"]


def main() -> int:
    app = QApplication(sys.argv)  # QSvgRenderer needs a QApplication alive
    ok = True

    for name in EXPECTED:
        path = ICON_DIR / name
        if not path.exists():
            print(f"MISSING  {name}")
            ok = False
            continue

        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            print(f"INVALID  {name}  (QSvgRenderer rejected it)")
            ok = False
            continue

        size = renderer.defaultSize()
        if size.width() <= 0 or size.height() <= 0:
            print(f"EMPTY    {name}  (default size is {size})")
            ok = False
            continue

        print(f"OK       {name}  ({size.width()}x{size.height()})")

    print("ALL OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())