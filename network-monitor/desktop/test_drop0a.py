"""
Test A for Drop 0a: verify that opening a pre-M8-style (CLI-shaped)
database through Database() does not delete any devices or logs.

Before Drop 0a, Database.__init__ called _purge_orphaned_devices, which
deleted every device with no topology_positions row and cascaded to
logs. On a CLI database (no topology_positions table at all), that
wiped everything. This test builds such a database with the *full* pre-M8
schema, so Database.__init__ completes successfully and the code path
we care about actually runs.

Run from desktop/: python3 test_drop0a.py
"""

import os
import sqlite3
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

TEST_DB = "data/test_cli_style.db"


# The pre-M8 CLI schema, verbatim from _initialize_schema minus the two
# desktop columns (device_type, monitoring_enabled) and the two desktop
# tables (topology_positions, connections). This is what a CLI database
# created by the pre-M8 code looks like on disk.
PRE_M8_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 2,
    timeout INTEGER NOT NULL DEFAULT 2,
    max_latency_ms REAL DEFAULT 300.0,
    critical_latency_ms REAL DEFAULT 800.0,
    max_jitter_ms REAL DEFAULT 150.0,
    packet_loss_threshold REAL DEFAULT 10.0,
    status TEXT DEFAULT 'UNKNOWN',
    down_since TIMESTAMP,
    last_down_alert_sent_at TIMESTAMP,
    last_recovery_alert_sent_at TIMESTAMP,
    last_erratic_alert_sent_at TIMESTAMP,
    initial_alert_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    is_reachable BOOLEAN NOT NULL,
    latency_ms REAL,
    min_latency_ms REAL,
    max_latency_ms REAL,
    avg_latency_ms REAL,
    packet_loss_percent REAL,
    fail_count INTEGER NOT NULL,
    retry_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    status_changed BOOLEAN NOT NULL DEFAULT 0,
    transition_type TEXT,
    quality_score REAL,
    quality_level TEXT,
    degradation_type TEXT,
    jitter_ms REAL,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS state_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    transition_type TEXT NOT NULL,
    latency_ms REAL,
    quality_score REAL,
    degradation_type TEXT,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS alert_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status_at_time TEXT
);
CREATE TABLE IF NOT EXISTS device_check_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    status TEXT NOT NULL,
    is_reachable BOOLEAN,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_logs_device_id ON logs(device_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_status_changed ON logs(status_changed);
CREATE INDEX IF NOT EXISTS idx_logs_quality ON logs(quality_score);
CREATE INDEX IF NOT EXISTS idx_changes_device_id ON state_changes(device_id);
CREATE INDEX IF NOT EXISTS idx_changes_timestamp ON state_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_tracking_device ON alert_tracking(device_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_check_history_device ON device_check_history(device_id, recorded_at);
"""


def build_cli_style_db(path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        p = path + suffix
        if os.path.exists(p):
            os.remove(p)

    conn = sqlite3.connect(path)
    conn.executescript(PRE_M8_SCHEMA)
    # Three devices, with logs and state changes, so any cascade has
    # something to destroy if the purge is still present.
    conn.executescript("""
        INSERT INTO devices (device_id, name, ip_address, status)
        VALUES ('a', 'router', '10.0.0.1', 'UP');
        INSERT INTO devices (device_id, name, ip_address, status)
        VALUES ('b', 'switch', '10.0.0.2', 'UP');
        INSERT INTO devices (device_id, name, ip_address, status)
        VALUES ('c', 'server', '10.0.0.3', 'DOWN');

        INSERT INTO logs (device_id, timestamp, is_reachable, fail_count, retry_count, status)
        VALUES ('a', '2026-01-01T00:00:00', 1, 0, 1, 'UP'),
               ('a', '2026-01-01T00:05:00', 1, 0, 1, 'UP'),
               ('b', '2026-01-01T00:00:00', 1, 0, 1, 'UP'),
               ('c', '2026-01-01T00:00:00', 0, 2, 2, 'DOWN'),
               ('c', '2026-01-01T00:05:00', 0, 2, 2, 'DOWN');

        INSERT INTO state_changes (device_id, timestamp, to_status, transition_type)
        VALUES ('a', '2026-01-01T00:00:00', 'UP', 'initial'),
               ('c', '2026-01-01T00:00:00', 'DOWN', 'down');
    """)
    conn.commit()
    conn.close()


def main() -> int:
    print(f"Building {TEST_DB} with full pre-M8 schema ...")
    build_cli_style_db(TEST_DB)

    # This is the operation that used to wipe the file. It must not.
    from app.database.db import Database

    print("Opening with Database() ...")
    Database(TEST_DB)

    conn = sqlite3.connect(TEST_DB)
    devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    logs = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    state_changes = conn.execute("SELECT COUNT(*) FROM state_changes").fetchone()[0]
    conn.close()

    print(f"devices={devices}, logs={logs}, state_changes={state_changes}")
    assert devices == 3, f"FAIL: devices wiped, expected 3, got {devices}"
    assert logs == 5, f"FAIL: logs wiped, expected 5, got {logs}"
    assert state_changes == 2, f"FAIL: state_changes wiped, expected 2, got {state_changes}"
    print("PASS: devices=3, logs=5, state_changes=2 untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())