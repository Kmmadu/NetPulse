#!/usr/bin/env python3
"""
Database Layer - SQLite Management
NetPulse Network Monitoring System - Production Ready with Thread Safety
"""

import sqlite3
import os
import time
import logging
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
from threading import local

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Database:
    """
    SQLite database manager with thread-safe connection pooling,
    WAL mode, and production-ready error handling.
    """
    
    def __init__(self, db_path: str = "data/monitor.db", timeout: int = 30):
        self.db_path = db_path
        self.timeout = timeout
        self._local = local()  # Thread-local storage for connections
        self._ensure_db_directory()
        self._initialize_schema()
        self._configure_connection_pragmas()
        self._ensure_status_column()  # Ensure status column exists
    
    def _ensure_db_directory(self):
        """Ensure database directory exists"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created database directory: {db_dir}")
            except OSError as e:
                logger.error(f"Failed to create database directory {db_dir}: {e}")
                raise
    
    def _ensure_status_column(self):
        """Ensure status column exists in devices table"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(devices)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'status' not in columns:
                    cursor.execute("ALTER TABLE devices ADD COLUMN status TEXT DEFAULT 'UNKNOWN'")
                    logger.info("✅ Added status column to devices table")
        except Exception as e:
            logger.warning(f"Could not ensure status column: {e}")
    
    def _ensure_devices_synced(self, device_id: str, name: str, ip_address: str):
        """Ensure device exists in devices table (for foreign key constraints)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO devices (device_id, name, ip_address, status)
                    VALUES (?, ?, ?, 'UNKNOWN')
                """, (device_id, name, ip_address))
                if cursor.rowcount > 0:
                    logger.debug(f"Auto-created device record for {name}")
        except Exception as e:
            logger.warning(f"Could not ensure device in devices table: {e}")
    
    def _get_raw_connection(self):
        """
        Create a raw SQLite connection with production settings.
        Uses thread-safe check_same_thread=False for multithreading.
        """
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=False,  # Allow usage across threads (with proper locking)
            isolation_level=None  # Autocommit mode for better concurrency
        )
        conn.row_factory = sqlite3.Row
        return conn
    
    def _configure_connection(self, conn: sqlite3.Connection):
        """
        Configure connection with production pragmas.
        Must be called on each connection.
        """
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Enforce foreign keys
        conn.execute("PRAGMA foreign_keys=ON")
        
        # Set busy timeout for concurrent access
        conn.execute(f"PRAGMA busy_timeout={self.timeout * 1000}")
        
        # Optimize for performance
        conn.execute("PRAGMA cache_size=-20000")  # 20MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA synchronous=NORMAL")  # Good balance safety/performance
        conn.execute("PRAGMA wal_autocheckpoint=1000")  # Checkpoint every 1000 pages
        
        # Enable memory-mapped I/O for large databases
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB
        
        # Set application ID for identification
        conn.execute("PRAGMA application_id=0x4E455450")  # 'NETP' in hex
        
        logger.debug(f"Configured connection: WAL mode, foreign keys ON, busy_timeout={self.timeout}s")
    
    def _configure_connection_pragmas(self):
        """
        Configure persistent pragmas at the database level.
        This runs once with a temporary connection.
        """
        try:
            with self._get_raw_connection() as conn:
                self._configure_connection(conn)
                logger.info(f"Database configured at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to configure database pragmas: {e}")
    
    @contextmanager
    def get_connection(self):
        """
        Get a thread-local connection with context manager.
        Each thread gets its own connection for thread safety.
        """
        # Get or create thread-local connection
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = self._get_raw_connection()
            self._configure_connection(self._local.connection)
            logger.debug(f"Created new database connection for thread {threading.get_ident()}")
        
        conn = self._local.connection
        
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction failed, rolling back: {e}")
            raise
        finally:
            # Don't close thread-local connections here; keep for reuse
            pass
    
    def close_all_connections(self):
        """Close all thread-local connections (call on shutdown)"""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
                logger.info("Closed database connection")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
            finally:
                self._local.connection = None
    
    def _initialize_schema(self):
        """Create tables with support for multi-ping results"""
        schema = """
        -- Devices table
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
        
        -- Logs table with multi-ping support
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
        
        -- State changes table
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
        
        -- Alert tracking table
        CREATE TABLE IF NOT EXISTS alert_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status_at_time TEXT
        );
        
        -- Device check history for erratic detection
        CREATE TABLE IF NOT EXISTS device_check_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL,
            is_reachable BOOLEAN,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_logs_device_id ON logs(device_id);
        CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_logs_status_changed ON logs(status_changed);
        CREATE INDEX IF NOT EXISTS idx_logs_quality ON logs(quality_score);
        CREATE INDEX IF NOT EXISTS idx_changes_device_id ON state_changes(device_id);
        CREATE INDEX IF NOT EXISTS idx_changes_timestamp ON state_changes(timestamp);
        CREATE INDEX IF NOT EXISTS idx_alert_tracking_device ON alert_tracking(device_id, sent_at);
        CREATE INDEX IF NOT EXISTS idx_check_history_device ON device_check_history(device_id, recorded_at);
        """
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executescript(schema)
                logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}")
            raise
    
    def _now_iso(self) -> str:
        """Return current timestamp in ISO format with second precision"""
        return datetime.now().replace(microsecond=0).isoformat()
    
    def add_log(self, log_data: Dict) -> int:
        """Add a check result with multi-ping support - production ready"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Safely extract ping result data
                ping_result = log_data.get('ping_result', {})
                if not isinstance(ping_result, dict):
                    ping_result = {}
                
                # Extract values with safe defaults
                device_id = log_data.get('device_id', 'unknown')
                
                # Ensure device exists in devices table (for foreign key)
                name = log_data.get('name', device_id)
                ip = log_data.get('ip', 'unknown')
                self._ensure_devices_synced(device_id, name, ip)
                
                timestamp = log_data.get('timestamp', datetime.now())
                
                # Format timestamp as ISO string if it's a datetime object
                if isinstance(timestamp, datetime):
                    timestamp = timestamp.isoformat()
                
                is_reachable = log_data.get('is_reachable', ping_result.get('is_reachable', False))
                latency_ms = log_data.get('latency_ms') or ping_result.get('avg_latency_ms')
                min_latency = ping_result.get('min_latency_ms')
                max_latency = ping_result.get('max_latency_ms')
                avg_latency = ping_result.get('avg_latency_ms')
                packet_loss = ping_result.get('packet_loss_percent', 0.0)
                
                # Quality data
                quality = log_data.get('quality')
                quality_score = None
                quality_level = None
                degradation_type = None
                jitter_ms = None
                
                if quality and isinstance(quality, dict):
                    quality_score = quality.get('quality_score')
                    quality_level = quality.get('quality_level')
                    degradation_type = quality.get('degradation_type')
                    if quality.get('metrics'):
                        jitter_ms = quality['metrics'].get('jitter_ms')
                
                # Status data
                current_status = log_data.get('current_status', 'UNKNOWN')
                fail_count = log_data.get('fail_count', 0)
                retry_count = log_data.get('retry_count', 1)
                status_changed = 1 if log_data.get('status_changed') else 0
                transition_type = log_data.get('transition_type')
                
                cursor.execute("""
                    INSERT INTO logs (
                        device_id, timestamp, is_reachable, latency_ms,
                        min_latency_ms, max_latency_ms, avg_latency_ms, packet_loss_percent,
                        fail_count, retry_count, status, status_changed, transition_type,
                        quality_score, quality_level, degradation_type, jitter_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id, timestamp, is_reachable, latency_ms,
                    min_latency, max_latency, avg_latency, packet_loss,
                    fail_count, retry_count, current_status, status_changed, transition_type,
                    quality_score, quality_level, degradation_type, jitter_ms
                ))
                
                last_id = cursor.lastrowid
                logger.debug(f"Added log entry {last_id} for device {device_id}")
                return last_id
                
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error in add_log: {e}")
            return -1
        except Exception as e:
            logger.error(f"Unexpected error in add_log: {e}", exc_info=True)
            return -1
    
    def add_state_change(self, change_data: Dict) -> int:
        """Add a state change record with retry on failure"""
        max_retries = 3
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    timestamp = change_data.get('timestamp', datetime.now())
                    if isinstance(timestamp, datetime):
                        timestamp = timestamp.isoformat()
                    
                    cursor.execute("""
                        INSERT INTO state_changes (
                            device_id, timestamp, from_status, to_status, 
                            transition_type, latency_ms, quality_score, degradation_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        change_data.get('device_id', 'unknown'),
                        timestamp,
                        change_data.get('from_status'),
                        change_data.get('to_status') or change_data.get('current_status'),
                        change_data.get('transition_type', 'unknown'),
                        change_data.get('latency_ms'),
                        change_data.get('quality_score'),
                        change_data.get('degradation_type')
                    ))
                    
                    last_id = cursor.lastrowid
                    logger.debug(f"Added state change {last_id}")
                    return last_id
                    
            except sqlite3.OperationalError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"State change insert failed, retrying: {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"State change insert failed after {max_retries} attempts: {e}")
                    return -1
            except Exception as e:
                logger.error(f"Unexpected error in add_state_change: {e}")
                return -1
        
        return -1
    
    # Device CRUD Operations
    
    def add_device(self, device_id: str, name: str, ip_address: str, 
                   retry_count: int = 2, timeout: int = 2,
                   max_latency_ms: float = 300.0,
                   critical_latency_ms: float = 800.0,
                   max_jitter_ms: float = 150.0,
                   packet_loss_threshold: float = 10.0) -> bool:
        """Add a new device to the database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO devices (
                        device_id, name, ip_address, retry_count, timeout,
                        max_latency_ms, critical_latency_ms, max_jitter_ms, packet_loss_threshold,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (device_id, name, ip_address, retry_count, timeout,
                      max_latency_ms, critical_latency_ms, max_jitter_ms, packet_loss_threshold,
                      self._now_iso(), self._now_iso()))
                logger.info(f"Added device: {name} ({ip_address})")
                return True
        except sqlite3.IntegrityError:
            logger.warning(f"Device {device_id} already exists")
            return False
        except Exception as e:
            logger.error(f"Error adding device {name}: {e}")
            return False
    
    def get_device(self, device_id: str) -> Optional[Dict]:
        """Retrieve a single device by ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting device {device_id}: {e}")
            return None
    
    def get_all_devices(self) -> List[Dict]:
        """Retrieve all devices"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM devices ORDER BY name")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all devices: {e}")
            return []
    
    def update_device(self, device_id: str, **kwargs) -> bool:
        """Update device fields"""
        allowed_fields = {
            'name', 'ip_address', 'retry_count', 'timeout',
            'max_latency_ms', 'critical_latency_ms', 'max_jitter_ms', 
            'packet_loss_threshold', 'down_since', 'initial_alert_sent',
            'last_down_alert_sent_at', 'last_recovery_alert_sent_at', 'last_erratic_alert_sent_at'
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [device_id, self._now_iso()]
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE devices 
                    SET {set_clause}, updated_at = ?
                    WHERE device_id = ?
                """, values)
                success = cursor.rowcount > 0
                if success:
                    logger.debug(f"Updated device {device_id}")
                return success
        except Exception as e:
            logger.error(f"Error updating device {device_id}: {e}")
            return False
    
    def delete_device(self, device_id: str) -> bool:
        """Delete a device and all its logs (cascade delete)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"Deleted device {device_id}")
                return success
        except Exception as e:
            logger.error(f"Error deleting device {device_id}: {e}")
            return False
    
    # ============================================================
    # CRITICAL: Sync Device State Between Memory and Database
    # ============================================================
    
    def sync_device_state(self, device_id: str, status: str, down_since: Optional[datetime] = None) -> bool:
        """
        Sync device state between memory and database.
        This ensures down_since and status are consistent across restarts.
        
        Args:
            device_id: The device identifier
            status: Current device status (UP/DOWN/DEGRADED)
            down_since: Timestamp when device went DOWN (None if not DOWN)
        
        Returns:
            True if sync successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Ensure status column exists (for older databases)
                cursor.execute("PRAGMA table_info(devices)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'status' not in columns:
                    cursor.execute("ALTER TABLE devices ADD COLUMN status TEXT DEFAULT 'UNKNOWN'")
                
                if down_since:
                    down_since_str = down_since.isoformat() if isinstance(down_since, datetime) else down_since
                    cursor.execute("""
                        UPDATE devices 
                        SET status = ?, down_since = ?, updated_at = ?
                        WHERE device_id = ?
                    """, (status, down_since_str, self._now_iso(), device_id))
                else:
                    cursor.execute("""
                        UPDATE devices 
                        SET status = ?, down_since = NULL, updated_at = ?
                        WHERE device_id = ?
                    """, (status, self._now_iso(), device_id))
                
                # If device not found, insert it
                if cursor.rowcount == 0:
                    # Try to get device info from user_devices via a query
                    cursor.execute("""
                        INSERT OR IGNORE INTO devices (device_id, name, ip_address, status, down_since)
                        SELECT device_id, name, ip_address, ?, ?
                        FROM user_devices WHERE device_id = ?
                    """, (status, down_since_str if down_since else None, device_id))
                    
                    if cursor.rowcount == 0:
                        logger.warning(f"Device {device_id} not found for state sync")
                        return False
                
                logger.debug(f"Synced device state for {device_id}: status={status}")
                return True
                
        except Exception as e:
            logger.error(f"Error syncing device state for {device_id}: {e}")
            return False
    
    def get_device_state(self, device_id: str) -> Optional[Dict]:
        """
        Get current device state from database.
        Useful for recovering state after restart.
        
        Returns:
            Dict with 'status' and 'down_since' keys, or None if not found
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT status, down_since FROM devices WHERE device_id = ?
                """, (device_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'status': row['status'],
                        'down_since': row['down_since']
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting device state for {device_id}: {e}")
            return None
    
    def sync_all_user_devices(self, user_id: int):
        """Sync all user devices to the devices table"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO devices (device_id, name, ip_address, status)
                    SELECT device_id, name, ip_address, 'UNKNOWN'
                    FROM user_devices WHERE user_id = ?
                """, (user_id,))
                logger.info(f"Synced user {user_id} devices to devices table")
        except Exception as e:
            logger.error(f"Error syncing user devices: {e}")
    
    # Query Operations
    
    def get_device_logs(self, device_id: str, limit: int = 100, 
                        offset: int = 0) -> List[Dict]:
        """Get recent logs for a specific device"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM logs 
                    WHERE device_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ? OFFSET ?
                """, (device_id, limit, offset))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting logs for {device_id}: {e}")
            return []
    
    def get_device_state_changes(self, device_id: str, 
                                 limit: int = 100) -> List[Dict]:
        """Get state change history for a device"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM state_changes 
                    WHERE device_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (device_id, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting state changes for {device_id}: {e}")
            return []
    
    def get_all_state_changes(self, since: Optional[datetime] = None,
                              limit: int = 100) -> List[Dict]:
        """Get recent state changes across all devices"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if since:
                    since_str = since.isoformat() if isinstance(since, datetime) else since
                    cursor.execute("""
                        SELECT * FROM state_changes 
                        WHERE timestamp >= ? 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    """, (since_str, limit))
                else:
                    cursor.execute("""
                        SELECT * FROM state_changes 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting state changes: {e}")
            return []
    
    def get_uptime_stats(self, device_id: str, days: int = 7) -> Optional[Dict]:
        """Calculate uptime statistics for a device"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_checks,
                        SUM(CASE WHEN status IN ('UP', 'DEGRADED') THEN 1 ELSE 0 END) as available_checks,
                        SUM(CASE WHEN status = 'UP' THEN 1 ELSE 0 END) as perfect_checks,
                        COUNT(DISTINCT DATE(timestamp)) as days_with_data
                    FROM logs 
                    WHERE device_id = ? 
                    AND timestamp >= datetime('now', ?)
                """, (device_id, f'-{days} days'))
                
                row = cursor.fetchone()
                if row and row['total_checks'] > 0:
                    availability = (row['available_checks'] / row['total_checks']) * 100
                    uptime = (row['perfect_checks'] / row['total_checks']) * 100
                    return {
                        'device_id': device_id,
                        'days': days,
                        'total_checks': row['total_checks'],
                        'available_checks': row['available_checks'],
                        'perfect_checks': row['perfect_checks'],
                        'availability_percentage': round(availability, 2),
                        'uptime_percentage': round(uptime, 2),
                        'days_with_data': row['days_with_data']
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting uptime stats for {device_id}: {e}")
            return None
    
    # Maintenance
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """Delete logs older than specified days"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cutoff = f"datetime('now', '-{days} days')"
                cursor.execute(f"DELETE FROM logs WHERE timestamp < {cutoff}")
                deleted = cursor.rowcount
                logger.info(f"Deleted {deleted} old logs (older than {days} days)")
                return deleted
        except Exception as e:
            logger.error(f"Error cleaning up old logs: {e}")
            return 0
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                stats = {}
                
                cursor.execute("SELECT COUNT(*) as count FROM devices")
                stats['device_count'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM logs")
                stats['log_count'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM state_changes")
                stats['state_change_count'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM alert_tracking")
                stats['alert_count'] = cursor.fetchone()['count']
                
                if os.path.exists(self.db_path):
                    stats['db_size_bytes'] = os.path.getsize(self.db_path)
                    stats['db_size_mb'] = round(stats['db_size_bytes'] / (1024 * 1024), 2)
                
                # Check WAL mode status
                cursor.execute("PRAGMA journal_mode")
                stats['journal_mode'] = cursor.fetchone()[0]
                
                return stats
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}
    
    def vacuum(self):
        """Optimize database (run during maintenance)"""
        try:
            with self.get_connection() as conn:
                conn.execute("VACUUM")
                logger.info("Database vacuum completed")
        except Exception as e:
            logger.error(f"Error during vacuum: {e}")
    
    def checkpoint_wal(self):
        """Force WAL checkpoint to truncate WAL file"""
        try:
            with self.get_connection() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.debug("WAL checkpoint completed")
        except Exception as e:
            logger.error(f"Error during WAL checkpoint: {e}")