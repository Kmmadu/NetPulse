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
        """Create tables if they don't exist with quality metrics support"""
        
        # Main schema with quality metrics columns
        schema = """
        -- Devices table: Stores all monitored devices with quality thresholds
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 2,
            timeout INTEGER NOT NULL DEFAULT 2,
            max_latency_ms REAL DEFAULT 100.0,
            critical_latency_ms REAL DEFAULT 500.0,
            max_jitter_ms REAL DEFAULT 50.0,
            packet_loss_threshold REAL DEFAULT 5.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Logs table: Stores every check result with quality metrics
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            is_reachable BOOLEAN NOT NULL,
            latency_ms REAL,
            fail_count INTEGER NOT NULL,
            retry_count INTEGER NOT NULL,
            status TEXT NOT NULL,  -- 'UP', 'DEGRADED', 'DOWN', or 'UNKNOWN'
            status_changed BOOLEAN NOT NULL DEFAULT 0,
            transition_type TEXT,
            quality_score REAL,
            quality_level TEXT,
            jitter_ms REAL,
            packet_loss_percent REAL,
            FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
        );
        
        -- State changes table: Only state transitions (for alerts/history)
        CREATE TABLE IF NOT EXISTS state_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            transition_type TEXT NOT NULL,
            latency_ms REAL,
            quality_score REAL,
            FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
        );
        
        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_logs_device_id ON logs(device_id);
        CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_logs_status_changed ON logs(status_changed);
        CREATE INDEX IF NOT EXISTS idx_logs_quality ON logs(quality_score);
        CREATE INDEX IF NOT EXISTS idx_changes_device_id ON state_changes(device_id);
        CREATE INDEX IF NOT EXISTS idx_changes_timestamp ON state_changes(timestamp);
        """
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(schema)
    
    # Device CRUD Operations with quality thresholds
    
    def add_device(self, device_id: str, name: str, ip_address: str, 
                   retry_count: int = 2, timeout: int = 2,
                   max_latency_ms: float = 100.0,
                   critical_latency_ms: float = 500.0,
                   max_jitter_ms: float = 50.0,
                   packet_loss_threshold: float = 5.0) -> bool:
        """
        Add a new device to the database with quality thresholds
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO devices (
                        device_id, name, ip_address, retry_count, timeout,
                        max_latency_ms, critical_latency_ms, max_jitter_ms, packet_loss_threshold
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (device_id, name, ip_address, retry_count, timeout,
                      max_latency_ms, critical_latency_ms, max_jitter_ms, packet_loss_threshold))
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
        
        Allowed kwargs: name, ip_address, retry_count, timeout,
                       max_latency_ms, critical_latency_ms, max_jitter_ms, packet_loss_threshold
        """
        allowed_fields = {
            'name', 'ip_address', 'retry_count', 'timeout',
            'max_latency_ms', 'critical_latency_ms', 'max_jitter_ms', 'packet_loss_threshold'
        }
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
    
    # Logging Operations with quality metrics
    
    def add_log(self, log_data: Dict) -> int:
        """
        Add a check result to the logs table with quality metrics
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs (
                    device_id, timestamp, is_reachable, latency_ms,
                    fail_count, retry_count, status, status_changed, transition_type,
                    quality_score, quality_level, jitter_ms, packet_loss_percent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_data['device_id'],
                log_data['timestamp'],
                log_data['is_reachable'],
                log_data.get('latency_ms'),
                log_data['fail_count'],
                log_data['retry_count'],
                log_data['status'],
                1 if log_data.get('status_changed') else 0,
                log_data.get('transition_type'),
                log_data.get('quality', {}).get('quality_score') if log_data.get('quality') else None,
                log_data.get('quality', {}).get('quality_level') if log_data.get('quality') else None,
                log_data.get('quality', {}).get('metrics', {}).get('jitter_ms') if log_data.get('quality') else None,
                log_data.get('quality', {}).get('metrics', {}).get('packet_loss_percent') if log_data.get('quality') else None
            ))
            return cursor.lastrowid
    
    def add_state_change(self, change_data: Dict) -> int:
        """
        Add a state change record with quality score
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO state_changes (
                    device_id, timestamp, from_status, to_status, 
                    transition_type, latency_ms, quality_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                change_data['device_id'],
                change_data['timestamp'],
                change_data.get('from_status'),
                change_data['to_status'],
                change_data['transition_type'],
                change_data.get('latency_ms'),
                change_data.get('quality_score')
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
            
            cursor.execute("SELECT COUNT(*) as count FROM devices")
            stats['device_count'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM logs")
            stats['log_count'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM state_changes")
            stats['state_change_count'] = cursor.fetchone()['count']
            
            if os.path.exists(self.db_path):
                stats['db_size_bytes'] = os.path.getsize(self.db_path)
                stats['db_size_mb'] = round(stats['db_size_bytes'] / (1024 * 1024), 2)
            
            return stats
