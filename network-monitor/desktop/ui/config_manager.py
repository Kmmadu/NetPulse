"""
Read, write, and apply desktop/.env configuration.

This module is the single place that touches desktop/.env. Everything else
(UI, worker) asks this module. Keeping the file I/O in one place means the
format details — quoting, line endings, which keys we write — are
reviewable in one file.

Public API:
    ENV_PATH                  — the absolute path to desktop/.env
    SMTP_KEYS                 — the six SMTP-related keys the dialog edits
    COOLDOWN_KEYS             — the four alert-cooldown keys the dialog edits
    read_env() -> dict        — parse the file into a dict (empty if missing)
    write_env(values: dict)   — write the given dict back to the file
    apply_to_process()        — load the file into os.environ for the
                                running process
    is_alerting_configured()  — True if AlertServiceV2 would construct
                                successfully with the current environment
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Dict


# Absolute path to the desktop app's .env file. desktop/ui/config_manager.py
# -> desktop/.env
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# The keys the config dialog edits. Read order in the dialog is this order.
SMTP_KEYS = (
    "SMTP_SERVER",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_TO",
)

COOLDOWN_KEYS = (
    "ALERT_DOWN_COOLDOWN",
    "ALERT_RECOVERY_COOLDOWN",
    "ALERT_ERRATIC_COOLDOWN",
    "ALERT_FLAPPING_SUPPRESSION",
)

ALL_EDITABLE_KEYS = SMTP_KEYS + COOLDOWN_KEYS


def read_env() -> Dict[str, str]:
    """
    Parse desktop/.env into a dict of key -> value.

    Handles the simple KEY=VALUE format python-dotenv writes and reads.
    Comments (lines starting with #) and blank lines are ignored. Values
    are returned as-is, without surrounding whitespace. A missing file
    returns an empty dict rather than raising — this is a first-run case,
    not an error.
    """
    if not ENV_PATH.exists():
        return {}

    values: Dict[str, str] = {}
    try:
        text = ENV_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[config_manager] could not read {ENV_PATH}: {exc!r}",
              file=sys.stderr)
        return {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes if present; the dialog never writes
        # quotes, but a user might have edited the file by hand.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value

    return values


def write_env(values: Dict[str, str]) -> None:
    """
    Write the given key -> value mapping to desktop/.env.

    Only keys in ALL_EDITABLE_KEYS are written; anything else in `values`
    is ignored. Any keys currently present in the file but not in
    ALL_EDITABLE_KEYS are preserved verbatim, so user-added keys (like
    ALERTS_ENABLED) survive a dialog edit.

    A clean file is written from scratch with a header comment and one
    line per key. This means hand-edited comments inside the file do not
    survive, but the file the dialog produces is readable and predictable.
    If preserving comments matters, that is a future improvement.
    """
    existing = read_env()

    lines = [
        "# NetPulse desktop app — SMTP alert configuration.",
        "# Written by the SMTP Configuration dialog. Edit via",
        "# Settings -> SMTP Configuration in the app, or edit this file",
        "# directly; both work. Contains a password; must not be committed.",
        "",
    ]

    for key in ALL_EDITABLE_KEYS:
        if key in values:
            value = values[key]
        elif key in existing:
            value = existing[key]
        else:
            value = ""
        lines.append(f"{key}={value}")

    # Preserve any non-editable keys the user has hand-added (e.g.
    # ALERTS_ENABLED). Written as a section at the bottom so they are
    # visibly distinct from the ones the dialog manages.
    preserved = {
        k: v for k, v in existing.items()
        if k not in ALL_EDITABLE_KEYS
    }
    if preserved:
        lines.append("")
        lines.append("# User-added keys, preserved by the dialog:")
        for key, value in preserved.items():
            lines.append(f"{key}={value}")

    lines.append("")

    try:
        ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        print(f"[config_manager] could not write {ENV_PATH}: {exc!r}",
              file=sys.stderr)
        raise


def apply_to_process() -> None:
    """
    Load desktop/.env into os.environ for the running process.

    This is what makes the "no restart needed" promise true. AlertServiceV2
    reads credentials via os.getenv() in __init__, and MonitoringEngine
    constructs a fresh AlertServiceV2 per alert. So after this call, the
    next alert will pick up the new values.

    override=True is deliberate: values in the file beat any stale ones
    already in os.environ from a previous load (which happens on module
    import of alert_v2, before the dialog ever runs).
    """
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_PATH, override=True)


def is_alerting_configured() -> bool:
    """
    Return True if AlertServiceV2 would construct successfully with the
    current environment.

    Reuses AlertServiceV2's own enabled check rather than re-deriving the
    logic (which would duplicate: presence of username, password, to_addrs;
    ALERTS_ENABLED flag; SMTP connection test). The banner it prints and
    the SMTP round trip it performs are captured/suppressed here so the
    check is silent and does not spam the terminal on every startup.

    Both stdout and stderr are captured. AlertServiceV2's banner goes to
    stdout, but its SMTP conversation uses set_debuglevel(1), which writes
    to stderr via smtplib. Capturing only stdout would let the SMTP trace
    reach the terminal, which is what we want to avoid for a silent
    configuration check.

    Constructing AlertServiceV2 performs a real SMTP connection test if
    credentials are present, which takes ~2 seconds. When credentials are
    missing, it returns early without a network call, so this is fast for
    the common first-run case.
    """
    # Local import to avoid a circular dependency at module load:
    # alert_v2 imports from app/, which imports app.database.db, which
    # is fine, but importing it from the top of this file would also
    # trigger load_dotenv at alert_v2's module level before we might want
    # to control that. Importing lazily keeps this module's import
    # side-effect-free.
    from app.services.alert_v2 import AlertServiceV2

    # Suppress both stdout and stderr during construction. The banner goes
    # to stdout; the SMTP conversation goes to stderr via smtplib's
    # set_debuglevel(1). Both are diagnostic noise for this check.
    out_buffer = io.StringIO()
    err_buffer = io.StringIO()
    try:
        with redirect_stdout(out_buffer), redirect_stderr(err_buffer):
            service = AlertServiceV2()
    except Exception:
        # Constructing AlertServiceV2 should not raise; it catches its own
        # errors. But if it does, treat as "not configured" rather than
        # crashing the caller.
        return False
    return bool(getattr(service, "_enabled", False))