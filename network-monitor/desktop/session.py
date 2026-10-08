"""
Session state for the desktop app.

Holds the small amount of state that must survive across launches but is
not part of any single topology file: which topology file was open when
the app last closed, and which directory the user last saved into (for
the Save As / Open file dialogs).

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


def _read_session_dict() -> dict:
    """
    Internal: read session.json and return its contents as a dict.

    Returns an empty dict if the file is missing, unreadable, or not a
    JSON object. Never raises. Callers are responsible for interpreting
    the keys they care about.
    """
    if not SESSION_FILE.exists():
        return {}
    try:
        raw = SESSION_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"[session] could not read {SESSION_FILE}: {exc!r}",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, dict):
        print(
            f"[session] {SESSION_FILE} is not a JSON object.",
            file=sys.stderr,
        )
        return {}
    return data


def _write_session_dict(data: dict) -> None:
    """
    Internal: write the given dict to session.json.

    Creates the data directory if missing. Failures are reported to
    stderr and swallowed — a failure to persist the session is a minor
    annoyance, not a reason to fail the operation that triggered it.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        SESSION_FILE.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"[session] could not write {SESSION_FILE}: {exc!r}",
            file=sys.stderr,
        )


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
    data = _read_session_dict()
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

    Read-merge-write: any other keys already in the session file (e.g.
    last_save_dir) are preserved. Without this, saving a topology would
    wipe the save-directory preference.
    """
    data = _read_session_dict()
    data["last_topology_path"] = str(path)
    _write_session_dict(data)


def load_last_save_dir() -> str:
    """
    Return the directory the file dialog should open in for Save As / Open.

    Resolution order:
      1. The 'last_save_dir' key in session.json, if present, non-empty,
         and the directory still exists.
      2. The directory containing the current topology file (i.e. the
         file's own folder), so the first Save As lands next to whatever
         you're already using.
      3. The user's home directory.

    Never raises. Any error is reported to stderr and treated as "no
    preference" — the dialog opens at home in that case, which is
    always correct even if not ideal.
    """
    data = _read_session_dict()
    d = data.get("last_save_dir")
    if isinstance(d, str) and d and Path(d).is_dir():
        return d

    # Fall back to the directory of the current topology file. That file
    # is either the session's stored path or the default, both of which
    # resolve to a directory we control.
    current = load_last_path()
    parent = Path(current).parent
    if parent.is_dir():
        return str(parent)

    # Last resort: home. Always exists.
    return str(Path.home())


def save_last_save_dir(path: str) -> None:
    """
    Record the directory the user last saved into.

    Called after a successful Save As or Open. Preserved alongside
    last_topology_path in session.json — both keys are read independently
    by load_last_path and load_last_save_dir, so neither is a required
    field.

    Failures are reported to stderr and swallowed, same as save_last_path.
    """
    data = _read_session_dict()
    data["last_save_dir"] = str(path)
    _write_session_dict(data)