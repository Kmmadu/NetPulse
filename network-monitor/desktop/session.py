"""
Session state for the desktop app.

Holds the small amount of state that must survive across launches but is
not part of any single topology file: currently just which topology file
was open when the app last closed.

Stored as JSON in desktop/data/session.json. If the file is missing,
unreadable, or malformed, the load functions return sensible defaults
rather than raising — a broken session file must never prevent the app
from starting. The only consequence of a lost session is that the app
opens the default topology instead of the last-used one.

Deliberately separate from config_manager (which handles .env / SMTP
settings). The two files have different lifecycles: .env is user-configured
and rarely changes, session.json is machine-state and changes on every
Open/Save-As. Keeping them apart means a corrupted session file cannot
break alerting, and vice versa.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


# desktop/session.py -> desktop/data/session.json
_DATA_DIR = Path(__file__).resolve().parent / "data"
SESSION_FILE = _DATA_DIR / "session.json"

# The default topology file. When no session exists (first run) or the
# session's path is missing/invalid, the app opens this file. It is also
# the file the pre-M9 code hardcoded, so users upgrading from M8 see no
# change on first launch: the session is created pointing at the same
# path the app used before.
DEFAULT_TOPOLOGY_PATH = str(_DATA_DIR / "desktop_monitor.db")


def load_last_path() -> str:
    """
    Return the path of the topology file to open on startup.

    Resolution order:
      1. The path stored in session.json, if the file exists, is valid
         JSON, contains a 'last_topology_path' key with a non-empty string
         value, and that path points at a file that actually exists on disk.
      2. DEFAULT_TOPOLOGY_PATH otherwise.

    The existence check matters: if the user opened a topology from a USB
    stick and later unplugged it, the session file would point at a path
    that no longer exists. Rather than failing on startup, we fall back to
    the default. The session file is rewritten with the default on the
    next successful save, so the stale path does not persist indefinitely.

    Never raises. Any I/O or parse error is reported to stderr and treated
    as "no session".
    """
    if not SESSION_FILE.exists():
        return DEFAULT_TOPOLOGY_PATH

    try:
        raw = SESSION_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"[session] could not read {SESSION_FILE}: {exc!r}; "
            f"using default topology path.",
            file=sys.stderr,
        )
        return DEFAULT_TOPOLOGY_PATH

    if not isinstance(data, dict):
        print(
            f"[session] {SESSION_FILE} is not a JSON object; "
            f"using default topology path.",
            file=sys.stderr,
        )
        return DEFAULT_TOPOLOGY_PATH

    path = data.get("last_topology_path")
    if not isinstance(path, str) or not path:
        return DEFAULT_TOPOLOGY_PATH

    if not Path(path).exists():
        # The stored path no longer points at a file. Fall back to the
        # default. The session file itself is left alone; it will be
        # overwritten the next time the user saves or opens something.
        print(
            f"[session] stored topology path no longer exists: {path}; "
            f"using default topology path.",
            file=sys.stderr,
        )
        return DEFAULT_TOPOLOGY_PATH

    return path


def save_last_path(path: str) -> None:
    """
    Record the given topology path as the one to open next launch.

    Called from File -> Save As and File -> Open once a topology file has
    been successfully written or loaded. Failures are reported to stderr
    and swallowed: a failure to persist the session is a minor annoyance
    (the user gets the default topology next launch instead of their last
    one), not a reason to fail the save/open operation that triggered it.

    Writes a small JSON object. Additional session fields can be added
    later without breaking existing readers, because load_last_path only
    reads the key it cares about.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"last_topology_path": str(path)}
    try:
        SESSION_FILE.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"[session] could not write {SESSION_FILE}: {exc!r}",
            file=sys.stderr,
        )