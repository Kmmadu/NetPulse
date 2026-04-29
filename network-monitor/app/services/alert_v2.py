#!/usr/bin/env python3
"""
Production Alert Service for NetPulse
Event-driven alerts only for meaningful state changes
"""

import smtplib
import os
import sqlite3
import socket
from datetime import datetime, timedelta
from typing import Dict, Optional
from contextlib import contextmanager
from pathlib import Path
from dotenv import load_dotenv

# Fix .env loading with absolute path
env_path = Path(__file__).parent.parent / '.env'  # app/services/ -> network-monitor/
if not env_path.exists():
    env_path = Path.cwd() / '.env'  # Fallback to current directory

load_dotenv(dotenv_path=env_path, override=True)
print(f"📁 Loading .env from: {env_path}")


class AlertType:
    DOWN = "down"
    RECOVERY = "recovery"
    ERRATIC = "erratic"


class AlertServiceV2:
    """Production-grade alert service - event-driven, no noise"""
    
    def __init__(self, db_path: str = "data/monitor.db"):
        self.db_path = db_path
        
        # Load from environment with debugging
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.username = os.getenv('SMTP_USERNAME', '')
        self.password = os.getenv('SMTP_PASSWORD', '')
        self.from_addr = os.getenv('SMTP_FROM', self.username)
        self.to_addrs = [addr.strip() for addr in os.getenv('SMTP_TO', '').split(',') if addr.strip()]
        
        # Read ALERTS_ENABLED flag
        alerts_enabled = os.getenv('ALERTS_ENABLED', 'true').lower() == 'true'
        
        # Cooldown settings (in minutes)
        self.down_cooldown_minutes = int(os.getenv('ALERT_DOWN_COOLDOWN', '5'))
        self.recovery_cooldown_minutes = int(os.getenv('ALERT_RECOVERY_COOLDOWN', '5'))
        self.erratic_cooldown_minutes = int(os.getenv('ALERT_ERRATIC_COOLDOWN', '30'))
        
        # Debug: Print configuration status
        print("\n" + "="*50)
        print("📧 Alert Service V2 - Configuration Debug")
        print("="*50)
        print(f"📁 .env path: {env_path}")
        print(f"📡 SMTP_SERVER: {self.smtp_server}")
        print(f"🔌 SMTP_PORT: {self.smtp_port}")
        print(f"👤 SMTP_USERNAME: {self.username}")
        print(f"🔑 SMTP_PASSWORD: {'✅ SET' if self.password else '❌ NOT SET'}")
        print(f"📤 SMTP_FROM: {self.from_addr}")
        print(f"📬 SMTP_TO: {self.to_addrs}")
        print(f"🎛️ ALERTS_ENABLED: {alerts_enabled}")
        print(f"⏱️ DOWN_COOLDOWN: {self.down_cooldown_minutes} min")
        print(f"⏱️ RECOVERY_COOLDOWN: {self.recovery_cooldown_minutes} min")
        print(f"⏱️ ERRATIC_COOLDOWN: {self.erratic_cooldown_minutes} min")
        print("="*50 + "\n")
        
        # Check if alerts are enabled by config
        if not alerts_enabled:
            self._enabled = False
            print("⚠️ Alert Service V2 DISABLED - ALERTS_ENABLED=false in .env")
            return
        
        # Check for missing configuration
        missing = []
        if not self.username:
            missing.append("SMTP_USERNAME")
        if not self.password:
            missing.append("SMTP_PASSWORD")
        if not self.to_addrs:
            missing.append("SMTP_TO")
        
        if missing:
            self._enabled = False
            print(f"❌ Alert Service V2 DISABLED - Missing environment variables: {', '.join(missing)}")
            print("   Please check your .env file")
            return
        
        self._enabled = self._check_enabled()
        self._init_db()
        
        if self._enabled:
            print(f"✅ Alert Service V2 ENABLED - sending to {', '.join(self.to_addrs)}")
        else:
            print("⚠️ Alert Service V2 DISABLED - SMTP connection test failed")
    
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
        """Real SMTP connection test - not just env var check"""
        print("\n" + "="*50)
        print("🔌 Running SMTP Connection Test")
        print("="*50)
        
        # First, check if we have the required config
        if not all([self.smtp_server, self.username, self.password, self.to_addrs]):
            missing = []
            if not self.smtp_server:
                missing.append("SMTP_SERVER")
            if not self.username:
                missing.append("SMTP_USERNAME")
            if not self.password:
                missing.append("SMTP_PASSWORD")
            if not self.to_addrs:
                missing.append("SMTP_TO")
            print(f"❌ Missing required config: {', '.join(missing)}")
            return False
        
        print(f"📡 Testing connection to {self.smtp_server}:{self.smtp_port}")
        
        # Test port connectivity first
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            result = sock.connect_ex((self.smtp_server, self.smtp_port))
            sock.close()
            
            if result != 0:
                print(f"❌ Port {self.smtp_port} is BLOCKED or unreachable (error code: {result})")
                print("   Possible causes:")
                print("   - Firewall blocking outbound SMTP")
                print("   - Network proxy restrictions")
                print("   - Internet connectivity issue")
                print("\n   To test manually, run:")
                print(f"   telnet {self.smtp_server} {self.smtp_port}")
                print(f"   or: nc -zv {self.smtp_server} {self.smtp_port}")
                return False
            else:
                print(f"✅ Port {self.smtp_port} is reachable")
        except Exception as e:
            print(f"❌ Port test failed: {e}")
            return False
        
        # Now test full SMTP connection
        try:
            print("🔄 Connecting to SMTP server...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
            server.set_debuglevel(1)  # Show SMTP conversation
            print("✅ SMTP connection established")
            
            # Identify ourselves
            server.ehlo()
            
            print("🔄 Starting TLS...")
            server.starttls()
            server.ehlo()  # Re-identify after TLS
            print("✅ TLS handshake complete")
            
            print("🔄 Authenticating...")
            server.login(self.username, self.password)
            print("✅ Authentication successful")
            
            print("🔄 Sending test quit...")
            server.quit()
            print("✅ SMTP test completed successfully")
            
            return True
            
        except socket.timeout:
            print("❌ SMTP test FAILED: Connection timeout")
            print("   Server took too long to respond")
            return False
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP test FAILED: Authentication error - {e}")
            print("   Troubleshooting:")
            print("   1. If using Gmail, ensure 2FA is enabled")
            print("   2. Generate an App Password (not your regular password)")
            print("   3. App Password should be 16 characters with no spaces")
            print("   4. Check that 'Allow less secure apps' is OFF (use App Password instead)")
            return False
        except smtplib.SMTPConnectError as e:
            print(f"❌ SMTP test FAILED: Cannot connect - {e}")
            print("   Troubleshooting:")
            print("   1. Check if SMTP server address is correct")
            print("   2. Verify network connectivity")
            print("   3. Try a different port (465 for SSL, 587 for TLS)")
            return False
        except smtplib.SMTPServerDisconnected as e:
            print(f"❌ SMTP test FAILED: Server disconnected - {e}")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP test FAILED: {type(e).__name__} - {e}")
            return False
        except Exception as e:
            print(f"❌ SMTP test FAILED: Unexpected error - {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _send_email(self, subject: str, body: str) -> bool:
        """Send email using configured SMTP server with real-time debugging"""
        if not self._enabled:
            print("❌ Email not sent - Alert service is disabled")
            return False
        
        print(f"\n📧 Attempting to send email...")
        print(f"   Subject: {subject[:50]}..." if len(subject) > 50 else f"   Subject: {subject}")
        print(f"   To: {', '.join(self.to_addrs)}")
        
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = self.from_addr
            msg['To'] = ', '.join(self.to_addrs)
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            print("   Connecting to SMTP server...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
            server.set_debuglevel(1)  # Enable SMTP debug output
            print(f"   ✅ Connected to {self.smtp_server}:{self.smtp_port}")
            
            # Identify ourselves to Gmail (helps with deliverability)
            server.ehlo()
            
            print("   Starting TLS...")
            server.starttls()
            server.ehlo()  # Re-identify after TLS
            print("   ✅ TLS established")
            
            print("   Logging in...")
            server.login(self.username, self.password)
            print(f"   ✅ Logged in as {self.username}")
            
            print("   Sending message...")
            server.send_message(msg)
            print("   ✅ Message sent")
            
            server.quit()
            print(f"✅ Alert sent successfully: {subject[:50]}...")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP Authentication Error: {e}")
            print("   Troubleshooting:")
            print("   • Verify your email and App Password are correct")
            print("   • App Password must be 16 characters with NO spaces")
            print("   • Enable 2FA on your Google account")
            print("   • Generate a new App Password at: https://myaccount.google.com/apppasswords")
            return False
        except smtplib.SMTPConnectError as e:
            print(f"❌ SMTP Connection Error: {e}")
            print(f"   Could not connect to {self.smtp_server}:{self.smtp_port}")
            print("   Check your network connection and firewall settings")
            return False
        except (smtplib.SMTPServerDisconnected, ConnectionResetError) as e:
            print(f"❌ SMTP Server Disconnected: {e}")
            print("   The server closed the connection unexpectedly")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP Error: {type(e).__name__}: {e}")
            return False
        except socket.timeout:
            print("❌ Connection timeout - server took too long to respond")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
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
    
    def process_status_change(self, device_id: str, old_status: str, new_status: str, is_reachable: bool = None):
        """
        Main entry point - called when device status changes.
        Event-driven logic - only 3 alert types.
        
        CRITICAL: Only triggers on actual state changes (old_status != new_status)
        """
        if not self._enabled:
            return
        
        # CRITICAL FIX: Only process if status actually changed
        if old_status == new_status:
            print(f"[ALERT_DEBUG] Skipping - no status change for {device_id}: {old_status} == {new_status}", flush=True)
            return
        
        # Record status for history
        self._record_status_history(device_id, new_status)
        
        # Get device info
        device = self._get_device_info(device_id)
        if not device:
            print(f"⚠️ Device not found: {device_id}")
            return
        
        print(f"[ALERT_DEBUG] Processing: {device['name']} - {old_status} → {new_status} (reachable={is_reachable})", flush=True)
        
        # Case 1: Device went DOWN (any state → DOWN)
        if new_status == "DOWN" and old_status != "DOWN":
            print(f"[ALERT_TRIGGER] 🔴 Device {device['name']} is DOWN - sending alert", flush=True)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE devices SET down_since = ? WHERE device_id = ?
                """, (datetime.now().isoformat(), device_id))
            
            self.send_down_alert(device_id, device['name'], device['ip_address'])
        
        # Case 2: Device recovered from DOWN (DOWN → UP or DOWN → DEGRADED)
        elif old_status == "DOWN" and new_status != "DOWN":
            down_since = device.get('down_since')
            downtime_seconds = 0
            
            if down_since:
                down_time = datetime.fromisoformat(down_since)
                downtime_seconds = int((datetime.now() - down_time).total_seconds())
                print(f"[ALERT_TRIGGER] 🟢 Device {device['name']} recovered after {downtime_seconds} seconds", flush=True)
                
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE devices SET down_since = NULL WHERE device_id = ?
                    """, (device_id,))
            
            self.send_recovery_alert(device_id, device['name'], device['ip_address'], downtime_seconds)
        
        # Case 3: Check for erratic behavior (flapping detection)
        if self._is_erratic(device_id):
            print(f"[ALERT_TRIGGER] ⚠️ Device {device['name']} is erratic", flush=True)
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
    
    def test_port_connectivity(self) -> Dict:
        """Test if SMTP port is reachable - diagnostic tool"""
        result = {
            'port': self.smtp_port,
            'server': self.smtp_server,
            'reachable': False,
            'error': None
        }
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            code = sock.connect_ex((self.smtp_server, self.smtp_port))
            sock.close()
            
            if code == 0:
                result['reachable'] = True
                print(f"✅ Port {self.smtp_port} is OPEN and reachable")
            else:
                result['error'] = f"Connection refused (error code: {code})"
                print(f"❌ Port {self.smtp_port} is BLOCKED or unreachable")
                print("   To test manually:")
                print(f"   telnet {self.smtp_server} {self.smtp_port}")
                print(f"   or: nc -zv {self.smtp_server} {self.smtp_port}")
        except socket.timeout:
            result['error'] = "Connection timeout"
            print(f"❌ Port {self.smtp_port} - Connection timeout")
        except Exception as e:
            result['error'] = str(e)
            print(f"❌ Port test failed: {e}")
        
        return result