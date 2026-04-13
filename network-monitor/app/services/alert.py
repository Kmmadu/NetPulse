#!/usr/bin/env python3
"""
Email Alert Service for NetPulse
Sends notifications for DOWN, DEGRADED, RECOVERY, and SUBOPTIMAL events
"""

import smtplib
import os
import time
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from contextlib import contextmanager


@dataclass
class AlertConfig:
    """Email alert configuration"""
    enabled: bool = True
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    to_emails: list = None
    
    # Alert cooldown settings (prevent spam)
    down_cooldown_minutes: int = 5
    degraded_cooldown_minutes: int = 15
    recovery_cooldown_minutes: int = 5
    suboptimal_cooldown_minutes: int = 30
    early_warning_cooldown_minutes: int = 60
    
    # Alert triggers
    alert_on_down: bool = True
    alert_on_degraded: bool = True
    alert_on_recovery: bool = True
    alert_on_suboptimal: bool = True
    alert_on_early_warning: bool = True
    
    # Quality thresholds for override
    down_success_rate_threshold: float = 30.0
    down_packet_loss_threshold: float = 50.0


class AlertService:
    """
    Email alert service for NetPulse monitoring system.
    Sends notifications with downtime duration and quality metrics.
    """
    
    def __init__(self, smtp_server: str = None, smtp_port: int = 587,
                 username: str = None, password: str = None,
                 from_addr: str = None, to_addrs: list = None,
                 user_id: int = None):
        """
        Initialize alert service with configuration.
        Can be called with explicit parameters or uses environment variables.
        """
        # Load from environment if not provided
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.username = username or os.getenv('SMTP_USERNAME', '')
        self.password = password or os.getenv('SMTP_PASSWORD', '')
        self.from_addr = from_addr or os.getenv('SMTP_FROM', self.username)
        self.user_id = user_id
        
        # Parse to_addrs from string or use provided list
        to_addrs_str = os.getenv('SMTP_TO', '')
        self.to_addrs = to_addrs or [addr.strip() for addr in to_addrs_str.split(',') if addr.strip()]
        
        # If user_id provided, load user's alert emails from database
        if self.user_id and not self.to_addrs:
            self._load_user_alert_emails()
        
        # Load additional configuration from environment
        self._load_config_from_env()
        
        # Tracking dictionaries
        self._cooldown = {}  # Track last alert time per device
        self._device_down_since = {}  # Track when a device went down
        self._device_degraded_since = {}  # Track when a device became degraded
        self._last_known_status = {}  # Track last status per device for deduplication
        
        self._enabled = self._check_enabled()
        
        if self._enabled:
            print(f"Email alerts enabled: sending to {', '.join(self.to_addrs)}")
        else:
            print("Email alerts disabled (configure SMTP_* environment variables to enable)")
    
    def _load_user_alert_emails(self):
        """Load alert emails for the user from database"""
        try:
            with sqlite3.connect("data/monitor.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT alert_email FROM users WHERE id = ?", (self.user_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    self.to_addrs = row[0].split(',')
        except Exception as e:
            print(f"Failed to load user alert emails: {e}")
    
    def _load_config_from_env(self):
        """Load additional configuration from environment variables"""
        self.down_cooldown_minutes = int(os.getenv('ALERT_DOWN_COOLDOWN', '5'))
        self.degraded_cooldown_minutes = int(os.getenv('ALERT_DEGRADED_COOLDOWN', '15'))
        self.recovery_cooldown_minutes = int(os.getenv('ALERT_RECOVERY_COOLDOWN', '5'))
        self.suboptimal_cooldown_minutes = int(os.getenv('ALERT_SUBOPTIMAL_COOLDOWN', '30'))
        self.early_warning_cooldown_minutes = int(os.getenv('ALERT_EARLY_WARNING_COOLDOWN', '60'))
        
        self.alert_on_down = os.getenv('ALERT_ON_DOWN', 'true').lower() == 'true'
        self.alert_on_degraded = os.getenv('ALERT_ON_DEGRADED', 'true').lower() == 'true'
        self.alert_on_recovery = os.getenv('ALERT_ON_RECOVERY', 'true').lower() == 'true'
        self.alert_on_suboptimal = os.getenv('ALERT_ON_SUBOPTIMAL', 'true').lower() == 'true'
        self.alert_on_early_warning = os.getenv('ALERT_ON_EARLY_WARNING', 'true').lower() == 'true'
        
        self.down_success_rate_threshold = float(os.getenv('DOWN_SUCCESS_RATE_THRESHOLD', '30.0'))
        self.down_packet_loss_threshold = float(os.getenv('DOWN_PACKET_LOSS_THRESHOLD', '50.0'))
    
    def _check_enabled(self) -> bool:
        """Check if email alerts are properly configured"""
        return (self.smtp_server and self.username and self.password and self.to_addrs)
    
    @contextmanager
    def _smtp_connection(self):
        """Context manager for SMTP connection - ensures proper cleanup"""
        server = None
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.username, self.password)
            yield server
        except Exception as e:
            print(f"SMTP connection error: {e}")
            raise
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    server.close()
    
    def _should_alert(self, device_id: str, alert_type: str, cooldown_minutes: int) -> bool:
        """Check if we should send an alert based on cooldown"""
        if not self._enabled:
            return False
        
        key = f"{device_id}:{alert_type}"
        last_time = self._cooldown.get(key, 0)
        cooldown_seconds = cooldown_minutes * 60
        current_time = time.time()
        
        if current_time - last_time >= cooldown_seconds:
            self._cooldown[key] = current_time
            return True
        
        return False
    
    def _format_duration(self, seconds: Optional[float]) -> str:
        """Format seconds into human-readable duration"""
        if not seconds or seconds <= 0:
            return "Unknown"
        
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            remaining_seconds = int(seconds % 60)
            if remaining_seconds > 0:
                return f"{minutes} minute{'s' if minutes != 1 else ''} and {remaining_seconds} second{'s' if remaining_seconds != 1 else ''}"
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = int(seconds / 3600)
            remaining_minutes = int((seconds % 3600) / 60)
            if remaining_minutes > 0:
                return f"{hours} hour{'s' if hours != 1 else ''} and {remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}"
            return f"{hours} hour{'s' if hours != 1 else ''}"
    
    def _send_email(self, subject: str, body: str) -> bool:
        """Send email using configured SMTP server with context manager"""
        if not self._enabled:
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.from_addr
            msg['To'] = ', '.join(self.to_addrs)
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            with self._smtp_connection() as server:
                server.send_message(msg)
            
            print(f"Alert sent: {subject}")
            return True
            
        except Exception as e:
            print(f"Failed to send email alert: {e}")
            return False
    
    def _merge_issues(self, result: Dict, quality: Dict) -> List[str]:
        """Safely merge issues from result and quality data"""
        issues = []
        
        # Get issues from quality
        if quality and quality.get('issues'):
            issues.extend(quality['issues'])
        if quality and quality.get('reasons'):
            issues.extend(quality['reasons'])
        
        # Add packet loss issue if present
        packet_loss = result.get('packet_loss_percent', 0)
        if packet_loss > 10:
            issues.append(f"High packet loss: {packet_loss:.1f}%")
        
        # Add latency issue if present
        latency = result.get('avg_latency_ms')
        if latency and latency > 100:
            issues.append(f"High latency: {latency:.0f}ms")
        
        # Add success rate issue if present
        success_rate = quality.get('success_rate', 100)
        if success_rate < 80:
            issues.append(f"Low success rate: {success_rate:.1f}%")
        
        return list(dict.fromkeys(issues))[:5]  # Remove duplicates, limit to 5
    
    def _get_quality_metrics(self, result: Dict) -> Dict:
        """Extract standardized quality metrics from result"""
        quality = result.get('quality', {})
        
        metrics = {
            'quality_score': quality.get('quality_score'),
            'success_rate': quality.get('success_rate', 100.0),
            'packet_loss_percent': result.get('packet_loss_percent', 0.0),
            'avg_latency_ms': result.get('avg_latency_ms'),
            'jitter_ms': quality.get('jitter_ms') or result.get('jitter_ms'),
            'degradation_type': quality.get('degradation_type', 'none'),
            'severity': quality.get('severity', 'unknown'),
            'issues': self._merge_issues(result, quality)
        }
        
        return metrics
    
    def _check_quality_overrides(self, metrics: Dict) -> Tuple[bool, str]:
        """
        Check if quality metrics override normal status.
        Returns (is_override, override_reason)
        """
        # Check success rate
        if metrics['success_rate'] < self.down_success_rate_threshold:
            return True, f"success rate is {metrics['success_rate']:.1f}% (below {self.down_success_rate_threshold}% threshold)"
        
        # Check packet loss
        if metrics['packet_loss_percent'] >= self.down_packet_loss_threshold:
            return True, f"packet loss is {metrics['packet_loss_percent']:.1f}% (above {self.down_packet_loss_threshold}% threshold)"
        
        return False, ""
    
    def _is_status_change_significant(self, device_id: str, new_status: str) -> bool:
        """
        Check if status change is significant enough to alert.
        Prevents duplicate alerts for the same state.
        """
        last_status = self._last_known_status.get(device_id)
        
        if last_status is None:
            self._last_known_status[device_id] = new_status
            return True
        
        if last_status == new_status:
            return False
        
        # Status changed, update tracking
        self._last_known_status[device_id] = new_status
        return True
    
    def _determine_alert_subject(self, alert_type: str, device_name: str, 
                                  metrics: Dict, downtime_str: str = "") -> str:
        """Generate appropriate subject line based on alert type and severity"""
        prefix = "[NetPulse]"
        
        if alert_type == "critical_down":
            return f"{prefix} CRITICAL: Device {device_name} is DOWN"
        
        elif alert_type == "down":
            return f"{prefix} ALERT: Device {device_name} is DOWN"
        
        elif alert_type == "recovery":
            return f"{prefix} RECOVERY: Device {device_name} is UP (Downtime: {downtime_str})"
        
        elif alert_type == "degraded":
            degradation = metrics.get('degradation_type', 'performance')
            severity = metrics.get('severity', 'moderate')
            
            if severity == 'severe':
                return f"{prefix} DEGRADED (SEVERE - {degradation.upper()}): {device_name}"
            elif severity == 'moderate':
                return f"{prefix} DEGRADED ({degradation.replace('_', ' ').title()}): {device_name}"
            else:
                return f"{prefix} DEGRADED: {device_name} - {degradation.replace('_', ' ').title()}"
        
        elif alert_type == "suboptimal":
            primary_issue = metrics['issues'][0] if metrics['issues'] else "performance issue"
            return f"{prefix} WARNING: {device_name} - {primary_issue[:50]}"
        
        elif alert_type == "early_warning":
            return f"{prefix} EARLY WARNING: {device_name} - Performance degrading"
        
        return f"{prefix} NOTIFICATION: {device_name} status changed"
    
    def _build_alert_body(self, alert_type: str, device_name: str, device_ip: str,
                          metrics: Dict, downtime_str: str = "",
                          transition_type: str = "", override_reason: str = "") -> str:
        """Build the email body content"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        body_lines = []
        body_lines.append("=" * 71)
        body_lines.append("NETPULSE NETWORK MONITORING SYSTEM")
        body_lines.append("=" * 71)
        body_lines.append("")
        
        if alert_type in ["critical_down", "down"]:
            body_lines.append("ALERT TYPE: DEVICE DOWN")
            if override_reason:
                body_lines.append(f"OVERRIDE REASON: {override_reason}")
        elif alert_type == "recovery":
            body_lines.append("ALERT TYPE: DEVICE RECOVERY")
        elif alert_type == "degraded":
            body_lines.append("ALERT TYPE: DEGRADED PERFORMANCE")
        elif alert_type == "suboptimal":
            body_lines.append("ALERT TYPE: SUBOPTIMAL PERFORMANCE")
        elif alert_type == "early_warning":
            body_lines.append("ALERT TYPE: EARLY WARNING - TRENDING DEGRADATION")
        
        body_lines.append("")
        body_lines.append("DEVICE INFORMATION:")
        body_lines.append("-" * 50)
        body_lines.append(f"  Device Name: {device_name}")
        body_lines.append(f"  IP Address: {device_ip}")
        body_lines.append(f"  Time: {timestamp}")
        if transition_type:
            body_lines.append(f"  Transition: {transition_type}")
        body_lines.append("")
        
        body_lines.append("PERFORMANCE METRICS:")
        body_lines.append("-" * 50)
        body_lines.append(f"  Quality Score: {metrics['quality_score']}/100" if metrics['quality_score'] else "  Quality Score: N/A")
        body_lines.append(f"  Success Rate: {metrics['success_rate']:.1f}%")
        body_lines.append(f"  Packet Loss: {metrics['packet_loss_percent']:.1f}%")
        if metrics['avg_latency_ms']:
            body_lines.append(f"  Average Latency: {metrics['avg_latency_ms']:.1f}ms")
        if metrics['jitter_ms']:
            body_lines.append(f"  Jitter: {metrics['jitter_ms']:.1f}ms")
        body_lines.append("")
        
        if metrics['issues']:
            body_lines.append("DETECTED ISSUES:")
            body_lines.append("-" * 50)
            for issue in metrics['issues'][:5]:
                body_lines.append(f"  - {issue}")
            if len(metrics['issues']) > 5:
                body_lines.append(f"  - ... and {len(metrics['issues']) - 5} more issues")
            body_lines.append("")
        
        if alert_type == "recovery" and downtime_str:
            body_lines.append("DOWNTIME SUMMARY:")
            body_lines.append("-" * 50)
            body_lines.append(f"  Total Downtime: {downtime_str}")
            body_lines.append("")
        
        if alert_type in ["critical_down", "down"]:
            body_lines.append("RECOMMENDED ACTIONS:")
            body_lines.append("-" * 50)
            body_lines.append("  1. Verify device power and network connectivity")
            body_lines.append("  2. Check device logs for errors")
            body_lines.append("  3. Verify IP address configuration")
            body_lines.append("  4. Check for network congestion or routing issues")
            body_lines.append("")
        
        elif alert_type == "degraded":
            body_lines.append("RECOMMENDED ACTIONS:")
            body_lines.append("-" * 50)
            body_lines.append("  1. Investigate network path for congestion")
            body_lines.append("  2. Check device CPU and memory utilization")
            body_lines.append("  3. Review recent configuration changes")
            body_lines.append("  4. Monitor for further degradation")
            body_lines.append("")
        
        body_lines.append("-" * 71)
        body_lines.append("NetPulse Network Monitoring System")
        body_lines.append("=" * 71)
        
        return "\n".join(body_lines)
    
    def _send_down_alert(self, result: Dict, metrics: Dict, override_reason: str = ""):
        """Send DOWN alert"""
        if not self.alert_on_down:
            return
        
        device_id = result.get('device_id', result.get('name'))
        device_name = result.get('name', 'Unknown')
        device_ip = result.get('ip', 'Unknown')
        
        if not self._should_alert(device_id, "down", self.down_cooldown_minutes):
            return
        
        # Determine alert severity
        is_critical = override_reason != "" or metrics['success_rate'] < 20 or metrics['packet_loss_percent'] > 70
        alert_type = "critical_down" if is_critical else "down"
        
        subject = self._determine_alert_subject(alert_type, device_name, metrics)
        body = self._build_alert_body(alert_type, device_name, device_ip, metrics,
                                      transition_type=result.get('transition_type', ''),
                                      override_reason=override_reason)
        
        self._send_email(subject, body)
    
    def _send_recovery_alert(self, result: Dict, metrics: Dict, downtime_seconds: Optional[float]):
        """Send RECOVERY alert"""
        if not self.alert_on_recovery:
            return
        
        device_id = result.get('device_id', result.get('name'))
        device_name = result.get('name', 'Unknown')
        device_ip = result.get('ip', 'Unknown')
        
        if not self._should_alert(device_id, "recovery", self.recovery_cooldown_minutes):
            return
        
        downtime_str = self._format_downtime(downtime_seconds)
        subject = self._determine_alert_subject("recovery", device_name, metrics, downtime_str)
        body = self._build_alert_body("recovery", device_name, device_ip, metrics, downtime_str,
                                      transition_type=result.get('transition_type', ''))
        
        self._send_email(subject, body)
    
    def _send_degraded_alert(self, result: Dict, metrics: Dict):
        """Send DEGRADED alert"""
        if not self.alert_on_degraded:
            return
        
        device_id = result.get('device_id', result.get('name'))
        device_name = result.get('name', 'Unknown')
        device_ip = result.get('ip', 'Unknown')
        
        if not self._should_alert(device_id, "degraded", self.degraded_cooldown_minutes):
            return
        
        subject = self._determine_alert_subject("degraded", device_name, metrics)
        body = self._build_alert_body("degraded", device_name, device_ip, metrics,
                                      transition_type=result.get('transition_type', ''))
        
        self._send_email(subject, body)
    
    def _send_suboptimal_alert(self, result: Dict, metrics: Dict):
        """Send SUBOPTIMAL alert (independent of status change)"""
        if not self.alert_on_suboptimal:
            return
        
        device_id = result.get('device_id', result.get('name'))
        device_name = result.get('name', 'Unknown')
        device_ip = result.get('ip', 'Unknown')
        
        if not self._should_alert(device_id, "suboptimal", self.suboptimal_cooldown_minutes):
            return
        
        subject = self._determine_alert_subject("suboptimal", device_name, metrics)
        body = self._build_alert_body("suboptimal", device_name, device_ip, metrics,
                                      transition_type=result.get('transition_type', ''))
        
        self._send_email(subject, body)
    
    def _send_early_warning_alert(self, result: Dict, metrics: Dict):
        """Send EARLY WARNING alert for trending degradation"""
        if not self.alert_on_early_warning:
            return
        
        device_id = result.get('device_id', result.get('name'))
        device_name = result.get('name', 'Unknown')
        device_ip = result.get('ip', 'Unknown')
        
        if not self._should_alert(device_id, "early_warning", self.early_warning_cooldown_minutes):
            return
        
        subject = self._determine_alert_subject("early_warning", device_name, metrics)
        body = self._build_alert_body("early_warning", device_name, device_ip, metrics,
                                      transition_type=result.get('transition_type', ''))
        
        self._send_email(subject, body)
    
    def send(self, result: Dict):
        """
        Main entry point - called when device status changes.
        Routes to appropriate alert methods based on explicit transitions.
        """
        if not self._enabled:
            return
        
        status_changed = result.get('status_changed', False)
        transition_type = result.get('transition_type', '')
        device_id = result.get('device_id', result.get('name'))
        current_status = result.get('current_status', 'UNKNOWN')
        
        # Get quality metrics
        metrics = self._get_quality_metrics(result)
        
        # Check for quality overrides (can force DOWN even if status says otherwise)
        is_override, override_reason = self._check_quality_overrides(metrics)
        
        # Handle DOWN transitions (explicit)
        if transition_type in ['up_to_down', 'degraded_to_down', 'initial_down'] or is_override:
            if self._is_status_change_significant(device_id, 'DOWN'):
                self._device_down_since[device_id] = datetime.now()
                self._device_degraded_since.pop(device_id, None)
                self._send_down_alert(result, metrics, override_reason)
            return
        
        # Handle RECOVERY transitions (explicit)
        if transition_type in ['down_to_up', 'degraded_to_up']:
            if self._is_status_change_significant(device_id, 'UP'):
                downtime_seconds = result.get('downtime_seconds')
                self._device_down_since.pop(device_id, None)
                self._device_degraded_since.pop(device_id, None)
                self._send_recovery_alert(result, metrics, downtime_seconds)
            return
        
        # Handle DEGRADED transitions (explicit)
        if transition_type in ['up_to_degraded', 'down_to_degraded', 'initial_degraded']:
            if self._is_status_change_significant(device_id, 'DEGRADED'):
                self._device_degraded_since[device_id] = datetime.now()
                self._send_degraded_alert(result, metrics)
            return
        
        # SUBOPTIMAL alerts (independent of status change - run even if status unchanged)
        if self.alert_on_suboptimal:
            quality = result.get('quality', {})
            is_suboptimal = quality.get('is_suboptimal', False)
            if is_suboptimal and metrics['quality_score'] and metrics['quality_score'] < 70:
                self._send_suboptimal_alert(result, metrics)
        
        # EARLY WARNING alerts (trend-based degradation)
        if self.alert_on_early_warning:
            quality = result.get('quality', {})
            early_warning = quality.get('early_warning', False)
            if early_warning:
                self._send_early_warning_alert(result, metrics)
    
    def send_test_alert(self) -> bool:
        """Send a test email to verify configuration"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        subject = "[NetPulse] Test Alert - Configuration Verified"
        body = f"""
=======================================================================
NETPULSE TEST ALERT
=======================================================================

This is a test message from your NetPulse monitoring system.

Email configuration is working correctly!

Configuration Details:
- SMTP Server: {self.smtp_server}
- From Email: {self.from_addr}
- To Emails: {', '.join(self.to_addrs)}
- Alert Time: {timestamp}

Alert Settings:
- DOWN Alerts: {self.alert_on_down}
- DEGRADED Alerts: {self.alert_on_degraded}
- RECOVERY Alerts: {self.alert_on_recovery}
- SUBOPTIMAL Alerts: {self.alert_on_suboptimal}
- EARLY WARNING Alerts: {self.alert_on_early_warning}

Cooldown Settings:
- DOWN Cooldown: {self.down_cooldown_minutes} minutes
- DEGRADED Cooldown: {self.degraded_cooldown_minutes} minutes
- RECOVERY Cooldown: {self.recovery_cooldown_minutes} minutes

=======================================================================
NetPulse Network Monitoring System
=======================================================================
"""
        return self._send_email(subject, body)