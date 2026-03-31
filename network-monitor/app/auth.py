#!/usr/bin/env python3
"""
User Authentication Module
NetPulse Network Monitoring System
"""

import hashlib
import secrets
import sqlite3
from typing import Optional, Dict
import os


class UserAuth:
    """Simple user authentication with hashed passwords"""
    
    def __init__(self, db_path: str = "data/monitor.db"):
        self.db_path = db_path
        self._init_tables()
    
    def _init_tables(self):
        """Initialize user tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    alert_email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS user_devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    device_group TEXT DEFAULT 'Default',
                    retry_count INTEGER DEFAULT 2,
                    max_latency_ms REAL DEFAULT 200.0,
                    packet_loss_threshold REAL DEFAULT 10.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, device_id)
                );
                
                CREATE TABLE IF NOT EXISTS user_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    group_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, group_name)
                );
            """)
    
    def _hash_password(self, password: str) -> str:
        """Hash password with salt"""
        salt = secrets.token_hex(16)
        return salt + ":" + hashlib.sha256((salt + password).encode()).hexdigest()
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        salt, hash_value = password_hash.split(":")
        return hash_value == hashlib.sha256((salt + password).encode()).hexdigest()
    
    def register(self, username: str, email: str, password: str) -> Optional[int]:
        """Register a new user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, self._hash_password(password))
                )
                user_id = cursor.lastrowid
                
                # Create default group
                cursor.execute(
                    "INSERT INTO user_groups (user_id, group_name) VALUES (?, ?)",
                    (user_id, "Default")
                )
                
                return user_id
        except sqlite3.IntegrityError:
            return None
    
    def login(self, username: str, password: str) -> Optional[Dict]:
        """Login user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE username = ? OR email = ?",
                (username, username)
            )
            user = cursor.fetchone()
            
            if user and self._verify_password(password, user['password_hash']):
                return dict(user)
            return None
    
    def update_alert_email(self, user_id: int, alert_email: str) -> bool:
        """Update user's alert email"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET alert_email = ? WHERE id = ?",
                (alert_email, user_id)
            )
            return cursor.rowcount > 0
    
    def get_user_devices(self, user_id: int) -> list:
        """Get all devices for a user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_devices WHERE user_id = ? ORDER BY device_group, name",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_user_groups(self, user_id: int) -> list:
        """Get all groups for a user"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT group_name FROM user_groups WHERE user_id = ? ORDER BY group_name",
                (user_id,)
            )
            return [row[0] for row in cursor.fetchall()]
    
    def add_user_device(self, user_id: int, name: str, ip: str, group: str = "Default") -> Optional[str]:
        """Add device for user"""
        device_id = name.lower().replace(' ', '_')
        
        # Check if group exists, create if not
        groups = self.get_user_groups(user_id)
        if group not in groups:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO user_groups (user_id, group_name) VALUES (?, ?)",
                    (user_id, group)
                )
        
        # Add device
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_devices (user_id, device_id, name, ip_address, device_group)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, device_id, name, ip, group))
            return device_id
        except sqlite3.IntegrityError:
            return None
    
    def update_user_device(self, user_id: int, device_id: str, name: str = None, ip: str = None, group: str = None) -> bool:
        """Update user device"""
        updates = []
        values = []
        if name:
            updates.append("name = ?")
            values.append(name)
        if ip:
            updates.append("ip_address = ?")
            values.append(ip)
        if group:
            updates.append("device_group = ?")
            values.append(group)
        
        if not updates:
            return False
        
        values.append(user_id)
        values.append(device_id)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE user_devices 
                SET {', '.join(updates)} 
                WHERE user_id = ? AND device_id = ?
            """, values)
            return cursor.rowcount > 0
    
    def delete_user_device(self, user_id: int, device_id: str) -> bool:
        """Delete user device"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM user_devices WHERE user_id = ? AND device_id = ?",
                (user_id, device_id)
            )
            return cursor.rowcount > 0