#!/usr/bin/env python3
"""
Database Layer - SQLite Management
NetPulse Network Monitoring System - Robust Multi-Ping Support
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager


class Database:
    """SQLite database manager with context manager support."""
    
    def __init__(self, db_path: str = "data/monitor.db"):
        self.db_path = db_path
        self._ensure_db_directory()
        self._initialize_schema()
    
    def _ensure_db_directory(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
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
    
    def add_log(self, log_data: Dict) -> int:
        """
        Add a check result with multi-ping support - robust version.
        Handles None values and missing fields gracefully.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Safely extract ping result data - handle None case
            ping_result = log_data.get('ping_result')
            if ping_result is None or not isinstance(ping_result, dict):
                ping_result = {}
            
            # Get latency values - handle both old and new formats
            latency_ms = log_data.get('latency_ms')
            if not latency_ms and ping_result:
                latency_ms = ping_result.get('avg_latency_ms')
            
            # Safe extraction with defaults
            min_latency = ping_result.get('min_latency_ms') if ping_result else None
            max_latency = ping_result.get('max_latency_ms') if ping_result else None
            avg_latency = ping_result.get('avg_latency_ms') if ping_result else None
            packet_loss = ping_result.get('packet_loss_percent', 0.0) if ping_result else 0.0
            
            # Determine is_reachable
            is_reachable = log_data.get('is_reachable')
            if is_reachable is None and ping_result:
                is_reachable = ping_result.get('is_reachable', False)
            if is_reachable is None:
                is_reachable = False
            
            # Get quality data - handle None
            quality = log_data.get('quality')
            quality_score = None
            quality_level = None
            degradation_type = None
            jitter_ms = None
            
            if quality and isinstance(quality, dict):
                quality_score = quality.get('quality_score')
                quality_level = quality.get('quality_level')
                degradation_type = quality.get('degradation_type')
                if quality.get('metrics') and isinstance(quality['metrics'], dict):
                    jitter_ms = quality['metrics'].get('jitter_ms')
            
            # Get device_id safely
            device_id = log_data.get('device_id', 'unknown')
            
            # Get timestamp safely
            timestamp = log_data.get('timestamp', datetime.now())
            
            # Get status safely
            current_status = log_data.get('current_status', 'UNKNOWN')
            
            # Get fail_count and retry_count safely
            fail_count = log_data.get('fail_count', 0)
            retry_count = log_data.get('retry_count', 1)
            
            # Get status_changed safely
            status_changed = 1 if log_data.get('status_changed') else 0
            
            # Get transition_type safely
            transition_type = log_data.get('transition_type')
            
            try:
                cursor.execute("""
                    INSERT INTO logs (
                        device_id, timestamp, is_reachable, latency_ms,
                        min_latency_ms, max_latency_ms, avg_latency_ms, packet_loss_percent,
                        fail_count, retry_count, status, status_changed, transition_type,
                        quality_score, quality_level, degradation_type, jitter_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id,
                    timestamp,
                    is_reachable,
                    latency_ms,
                    min_latency,
                    max_latency,
                    avg_latency,
                    packet_loss,
                    fail_count,
                    retry_count,
                    current_status,
                    status_changed,
                    transition_type,
                    quality_score,
                    quality_level,
                    degradation_type,
                    jitter_ms
                ))
                return cursor.lastrowid
            except Exception as e:
                # Log error but don't crash monitoring
                import sys
                print(f"Database error in add_log: {e}", file=sys.stderr)
                return -1
    
    def add_state_change(self, change_data: Dict) -> int:
        """Add a state change record with robust error handling"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT INTO state_changes (
                        device_id, timestamp, from_status, to_status, 
                        transition_type, latency_ms, quality_score, degradation_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    change_data.get('device_id', 'unknown'),
                    change_data.get('timestamp', datetime.now()),
                    change_data.get('from_status'),
                    change_data.get('to_status') or change_data.get('current_status'),
                    change_data.get('transition_type', 'unknown'),
                    change_data.get('latency_ms'),
                    change_data.get('quality_score'),
                    change_data.get('degradation_type')
                ))
                return cursor.lastrowid
            except Exception as e:
                import sys
                print(f"Database error in add_state_change: {e}", file=sys.stderr)
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
                        max_latency_ms, critical_latency_ms, max_jitter_ms, packet_loss_threshold
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (device_id, name, ip_address, retry_count, timeout,
                      max_latency_ms, critical_latency_ms, max_jitter_ms, packet_loss_threshold))
                return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"Error adding device: {e}")
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
        """Update device fields"""
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
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
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
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
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
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
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
    
    def vacuum(self):
        """Optimize database"""
        with self.get_connection() as conn:
            conn.execute("VACUUM")
