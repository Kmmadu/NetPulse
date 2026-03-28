#!/usr/bin/env python3
"""
Database Layer - SQLite Management
NetPulse Network Monitoring System
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager


class Database:
    """
    SQLite database manager with context manager support.
    Handles connections, schema creation, and basic operations.
    """
    
    def __init__(self, db_path: str = "data/monitor.db"):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_db_directory()
        self._initialize_schema()
    
    def _ensure_db_directory(self):
        """Ensure the data directory exists"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        Automatically handles commit/rollback.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _initialize_schema(self):
        """Create tables if they don't exist"""
        schema = """
        -- Devices table: Stores all monitored devices
        -- device_id is the primary key (string, unique)
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 2,
            timeout INTEGER NOT NULL DEFAULT 2,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Logs table: Stores every check result
        -- Indexed by device_id and timestamp for fast queries
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            is_reachable BOOLEAN NOT NULL,
            latency_ms REAL,
            fail_count INTEGER NOT NULL,
            retry_count INTEGER NOT NULL,
            status TEXT NOT NULL,  -- 'UP', 'DOWN', or 'UNKNOWN'
            status_changed BOOLEAN NOT NULL DEFAULT 0,
            transition_type TEXT,  -- 'initial_up', 'initial_down', 'up_to_down', 'down_to_up'
            FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
        );
        
        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_logs_device_id ON logs(device_id);
        CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_logs_status_changed ON logs(status_changed);
        
        -- State changes table: Only state transitions (for alerts/history)
        -- This is essentially a filtered view of logs, but stored separately for efficiency
        CREATE TABLE IF NOT EXISTS state_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            from_status TEXT,  -- 'UP', 'DOWN', or NULL
            to_status TEXT NOT NULL,  -- 'UP' or 'DOWN'
            transition_type TEXT NOT NULL,  -- 'up_to_down', 'down_to_up', 'initial_up', 'initial_down'
            latency_ms REAL,
            FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
        );
        
        CREATE INDEX IF NOT EXISTS idx_changes_device_id ON state_changes(device_id);
        CREATE INDEX IF NOT EXISTS idx_changes_timestamp ON state_changes(timestamp);
        """
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(schema)
    
    # Device CRUD Operations
    
    def add_device(self, device_id: str, name: str, ip_address: str, 
                   retry_count: int = 2, timeout: int = 2) -> bool:
        """
        Add a new device to the database
        
        Returns:
            bool: True if added successfully, False if duplicate
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO devices (device_id, name, ip_address, retry_count, timeout)
                    VALUES (?, ?, ?, ?, ?)
                """, (device_id, name, ip_address, retry_count, timeout))
                return True
        except sqlite3.IntegrityError:
            return False
    
    def get_device(self, device_id: str) -> Optional[Dict]:
        """Retrieve a single device by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_devices(self) -> List[Dict]:
        """Retrieve all devices"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM devices ORDER BY name")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_device(self, device_id: str, **kwargs) -> bool:
        """
        Update device fields
        
        Allowed kwargs: name, ip_address, retry_count, timeout
        """
        allowed_fields = {'name', 'ip_address', 'retry_count', 'timeout'}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [device_id]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE devices 
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE device_id = ?
            """, values)
            return cursor.rowcount > 0
    
    def delete_device(self, device_id: str) -> bool:
        """Delete a device and all its logs (cascade delete)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
            return cursor.rowcount > 0
    
    # Logging Operations
    
    def add_log(self, log_data: Dict) -> int:
        """
        Add a check result to the logs table
        
        Args:
            log_data: Dictionary with fields:
                - device_id
                - timestamp
                - is_reachable
                - latency_ms
                - fail_count
                - retry_count
                - status (UP/DOWN/UNKNOWN)
                - status_changed
                - transition_type (optional)
        
        Returns:
            int: Row ID of inserted log
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs (
                    device_id, timestamp, is_reachable, latency_ms,
                    fail_count, retry_count, status, status_changed, transition_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_data['device_id'],
                log_data['timestamp'],
                log_data['is_reachable'],
                log_data.get('latency_ms'),
                log_data['fail_count'],
                log_data['retry_count'],
                log_data['status'],
                1 if log_data.get('status_changed') else 0,
                log_data.get('transition_type')
            ))
            return cursor.lastrowid
    
    def add_state_change(self, change_data: Dict) -> int:
        """
        Add a state change record (for alerting)
        
        Args:
            change_data: Dictionary with fields:
                - device_id
                - timestamp
                - from_status (UP/DOWN/None)
                - to_status (UP/DOWN)
                - transition_type
                - latency_ms (optional)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO state_changes (
                    device_id, timestamp, from_status, to_status, 
                    transition_type, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                change_data['device_id'],
                change_data['timestamp'],
                change_data.get('from_status'),
                change_data['to_status'],
                change_data['transition_type'],
                change_data.get('latency_ms')
            ))
            return cursor.lastrowid
    
    # Query Operations
    
    def get_device_logs(self, device_id: str, limit: int = 100, 
                        offset: int = 0) -> List[Dict]:
        """Get recent logs for a specific device"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM logs 
                WHERE device_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
            """, (device_id, limit, offset))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_device_state_changes(self, device_id: str, 
                                 limit: int = 100) -> List[Dict]:
        """Get state change history for a device"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM state_changes 
                WHERE device_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (device_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_state_changes(self, since: Optional[datetime] = None,
                              limit: int = 100) -> List[Dict]:
        """Get recent state changes across all devices"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if since:
                cursor.execute("""
                    SELECT * FROM state_changes 
                    WHERE timestamp >= ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (since, limit))
            else:
                cursor.execute("""
                    SELECT * FROM state_changes 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_uptime_stats(self, device_id: str, days: int = 7) -> Dict:
        """Calculate uptime statistics for a device"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get total checks and successful checks in the last N days
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN is_reachable = 1 THEN 1 ELSE 0 END) as successful_checks,
                    COUNT(DISTINCT DATE(timestamp)) as days_with_data
                FROM logs 
                WHERE device_id = ? 
                AND timestamp >= datetime('now', ?)
            """, (device_id, f'-{days} days'))
            
            row = cursor.fetchone()
            if row and row['total_checks'] > 0:
                uptime = (row['successful_checks'] / row['total_checks']) * 100
                return {
                    'device_id': device_id,
                    'days': days,
                    'total_checks': row['total_checks'],
                    'successful_checks': row['successful_checks'],
                    'uptime_percentage': round(uptime, 2),
                    'days_with_data': row['days_with_data']
                }
            return None
    
    # Maintenance
    
    def cleanup_old_logs(self, days: int = 30):
        """Delete logs older than specified days"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM logs 
                WHERE timestamp < datetime('now', ?)
            """, (f'-{days} days',))
            return cursor.rowcount
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Device count
            cursor.execute("SELECT COUNT(*) as count FROM devices")
            stats['device_count'] = cursor.fetchone()['count']
            
            # Log count
            cursor.execute("SELECT COUNT(*) as count FROM logs")
            stats['log_count'] = cursor.fetchone()['count']
            
            # State change count
            cursor.execute("SELECT COUNT(*) as count FROM state_changes")
            stats['state_change_count'] = cursor.fetchone()['count']
            
            # Database size
            import os
            if os.path.exists(self.db_path):
                stats['db_size_bytes'] = os.path.getsize(self.db_path)
                stats['db_size_mb'] = round(stats['db_size_bytes'] / (1024 * 1024), 2)
            
            return stats
