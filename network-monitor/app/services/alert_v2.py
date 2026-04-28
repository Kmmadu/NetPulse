#!/usr/bin/env python3
"""
Production Alert Service for NetPulse
Event-driven alerts only for meaningful state changes
"""

import smtplib
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()


class AlertType:
    DOWN = "down"
    RECOVERY = "recovery"
    ERRATIC = "erratic"


class AlertServiceV2:
    """Production-grade alert service - event-driven, no noise"""
    
    def __init__(self, db_path: str = "data/monitor.db"):
        self.db_path = db_path
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.username = os.getenv('SMTP_USERNAME', '')
        self.password = os.getenv('SMTP_PASSWORD', '')
        self.from_addr = os.getenv('SMTP_FROM', self.username)
        self.to_addrs = [addr.strip() for addr in os.getenv('SMTP_TO', '').split(',') if addr.strip()]
        
        # Cooldown settings (in minutes)
        self.down_cooldown_minutes = int(os.getenv('ALERT_DOWN_COOLDOWN', '5'))
        self.recovery_cooldown_minutes = int(os.getenv('ALERT_RECOVERY_COOLDOWN', '5'))
        self.erratic_cooldown_minutes = int(os.getenv('ALERT_ERRATIC_COOLDOWN', '30'))
        
        self._enabled = self._check_enabled()
        self._init_db()
        
        if self._enabled:
            print(f"✅ Alert Service V2 enabled: sending to {', '.join(self.to_addrs)}")
        else:
            print("⚠️ Alert Service V2 disabled (configure SMTP_* in .env)")
    
    def _init_db(self):
        """Initialize database tables for alert tracking"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Add new columns to devices if not exist
            cursor.execute("PRAGMA table_info(devices)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'down_since' not in columns:
                cursor.execute("ALTER TABLE devices ADD COLUMN down_since TIMESTAMP")
            if 'last_down_alert_sent_at' not in columns:
                cursor.execute("ALTER TABLE devices ADD COLUMN last_down_alert_sent_at TIMESTAMP")
            if 'last_recovery_alert_sent_at' not in columns:
                cursor.execute("ALTER TABLE devices ADD COLUMN last_recovery_alert_sent_at TIMESTAMP")
            if 'last_erratic_alert_sent_at' not in columns:
                cursor.execute("ALTER TABLE devices ADD COLUMN last_erratic_alert_sent_at TIMESTAMP")
            
            # Create status history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_history_device 
                ON device_status_history(device_id, recorded_at)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def _check_enabled(self) -> bool:
        """Check if email alerts are properly configured"""
        return bool(self.smtp_server and self.username and self.password and self.to_addrs)
    
    def _send_email(self, subject: str, body: str) -> bool:
        """Send email using configured SMTP server"""
        if not self._enabled:
            return False
        
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = self.from_addr
            msg['To'] = ', '.join(self.to_addrs)
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            print(f"📧 Alert sent: {subject}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
            return False
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to human readable"""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''}"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''}"
        else:
            days = seconds // 86400
            return f"{days} day{'s' if days > 1 else ''}"
    
    def _record_status_history(self, device_id: str, status: str):
        """Record status change for erratic detection"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO device_status_history (device_id, status, recorded_at)
                VALUES (?, ?, ?)
            """, (device_id, status, datetime.now().isoformat()))
            
            # Keep only last 20 records per device
            cursor.execute("""
                DELETE FROM device_status_history 
                WHERE id NOT IN (
                    SELECT id FROM device_status_history 
                    WHERE device_id = ? 
                    ORDER BY recorded_at DESC 
                    LIMIT 20
                )
            """, (device_id,))
    
    def _is_erratic(self, device_id: str, checks_back: int = 10) -> bool:
        """Check if device has been flapping (frequent status changes)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status FROM device_status_history 
                WHERE device_id = ? 
                ORDER BY recorded_at DESC 
                LIMIT ?
            """, (device_id, checks_back))
            
            history = [row['status'] for row in cursor.fetchall()]
            
            if len(history) < checks_back:
                return False
            
            # Count status changes
            changes = 0
            for i in range(1, len(history)):
                if history[i] != history[i-1]:
                    changes += 1
            
            # Erratic if status changed 3 or more times in last 10 checks
            return changes >= 3
    
    def _should_send_alert(self, device_id: str, alert_type: str, cooldown_minutes: int) -> bool:
        """Check cooldown for alert type"""
        if cooldown_minutes == 0:
            return True
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            col_name = f"last_{alert_type}_alert_sent_at"
            cursor.execute(f"SELECT {col_name} FROM devices WHERE device_id = ?", (device_id,))
            row = cursor.fetchone()
            
            if not row or not row[0]:
                return True
            
            last_sent = datetime.fromisoformat(row[0])
            return datetime.now() - last_sent >= timedelta(minutes=cooldown_minutes)
    
    def _update_alert_timestamp(self, device_id: str, alert_type: str):
        """Update last alert timestamp"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            col_name = f"last_{alert_type}_alert_sent_at"
            cursor.execute(f"UPDATE devices SET {col_name} = ? WHERE device_id = ?", 
                          (datetime.now().isoformat(), device_id))
    
    def _get_device_info(self, device_id: str) -> Dict:
        """Get device information"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT device_id, name, ip_address, down_since 
                FROM devices WHERE device_id = ?
            """, (device_id,))
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    def send_down_alert(self, device_id: str, device_name: str, device_ip: str):
        """Send DOWN alert - only once when device goes down"""
        if not self._should_send_alert(device_id, "down", self.down_cooldown_minutes):
            return
        
        timestamp = datetime.now().strftime("%I:%M %p").lstrip('0')
        
        subject = f"[NetPulse] 🔴 Device Down – {device_name}"
        
        body = f"""
Device: {device_name}
IP Address: {device_ip}

Status: DOWN
Time: {timestamp}

What this means:
This device is currently unreachable or experiencing serious network issues.

What you can do:

• Check if the device is powered on
• Check network connection
• Contact your network administrator

---
NetPulse Network Monitoring
        """
        
        self._send_email(subject, body.strip())
        self._update_alert_timestamp(device_id, "down")
    
    def send_recovery_alert(self, device_id: str, device_name: str, device_ip: str, downtime_seconds: int):
        """Send RECOVERY alert when device comes back up"""
        if not self._should_send_alert(device_id, "recovery", self.recovery_cooldown_minutes):
            return
        
        duration = self._format_duration(downtime_seconds)
        timestamp = datetime.now().strftime("%I:%M %p").lstrip('0')
        
        subject = f"[NetPulse] 🟢 Device Restored – {device_name}"
        
        body = f"""
Device: {device_name}

Status: ONLINE
Recovered At: {timestamp}
Downtime: {duration}

Good news — the device is back online and working normally.

---
NetPulse Network Monitoring
        """
        
        self._send_email(subject, body.strip())
        self._update_alert_timestamp(device_id, "recovery")
    
    def send_erratic_alert(self, device_id: str, device_name: str, device_ip: str):
        """Send ERRATIC behavior warning (flapping detection)"""
        if not self._should_send_alert(device_id, "erratic", self.erratic_cooldown_minutes):
            return
        
        timestamp = datetime.now().strftime("%I:%M %p").lstrip('0')
        
        subject = f"[NetPulse] ⚠️ Unstable Device – {device_name}"
        
        body = f"""
Device: {device_name}

Status: UNSTABLE

This device has been going up and down repeatedly in a short time.

This may indicate:

• Unstable network connection
• Power issues
• Hardware problems

---
NetPulse Network Monitoring
        """
        
        self._send_email(subject, body.strip())
        self._update_alert_timestamp(device_id, "erratic")
    
    def process_status_change(self, device_id: str, old_status: str, new_status: str):
        """
        Main entry point - called when device status changes.
        Event-driven logic - only 3 alert types.
        """
        if not self._enabled:
            return
        
        # Record status for history
        self._record_status_history(device_id, new_status)
        
        # Get device info
        device = self._get_device_info(device_id)
        if not device:
            print(f"⚠️ Device not found: {device_id}")
            return
        
        print(f"🔵 Processing status change: {device['name']} - {old_status} → {new_status}")
        
        # Case 1: Device went DOWN
        if new_status == "DOWN" and old_status != "DOWN":
            print(f"🔴 Device {device['name']} is DOWN - sending alert")
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE devices SET down_since = ? WHERE device_id = ?
                """, (datetime.now().isoformat(), device_id))
            
            self.send_down_alert(device_id, device['name'], device['ip_address'])
        
        # Case 2: Device recovered from DOWN
        elif old_status == "DOWN" and new_status != "DOWN":
            down_since = device.get('down_since')
            downtime_seconds = 0
            
            if down_since:
                down_time = datetime.fromisoformat(down_since)
                downtime_seconds = int((datetime.now() - down_time).total_seconds())
                print(f"🟢 Device {device['name']} recovered after {downtime_seconds} seconds")
                
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE devices SET down_since = NULL WHERE device_id = ?
                    """, (device_id,))
            
            self.send_recovery_alert(device_id, device['name'], device['ip_address'], downtime_seconds)
        
        # Case 3: Check for erratic behavior
        if self._is_erratic(device_id):
            print(f"⚠️ Device {device['name']} is erratic")
            self.send_erratic_alert(device_id, device['name'], device['ip_address'])
    
    def send_test_alert(self) -> bool:
        """Send a test email to verify configuration"""
        timestamp = datetime.now().strftime("%I:%M %p").lstrip('0')
        
        subject = "[NetPulse] ✅ Test Alert – Configuration Verified"
        
        body = f"""
This is a test message from your NetPulse monitoring system.

Your email configuration is working correctly.

Time: {timestamp}

No action is required. This is only a test.

---
NetPulse Network Monitoring
        """
        
        return self._send_email(subject, body.strip())