#!/usr/bin/env python3
"""
Simple Email Alert Service
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict
import os


class AlertService:
    """Simple email alerts"""
    
    def __init__(self, smtp_server: str = None, smtp_port: int = 587,
                 username: str = None, password: str = None,
                 from_addr: str = None, to_addrs: list = None):
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.username = username or os.getenv('SMTP_USERNAME')
        self.password = password or os.getenv('SMTP_PASSWORD')
        self.from_addr = from_addr or os.getenv('SMTP_FROM', self.username)
        self.to_addrs = to_addrs or os.getenv('SMTP_TO', '').split(',')
        
        self._cooldown = {}  # Track last alert time per device
        self.cooldown_minutes = 5
    
    def _should_alert(self, device_id: str) -> bool:
        """Check if we should send alert (cooldown)"""
        from time import time
        last = self._cooldown.get(device_id, 0)
        if time() - last > self.cooldown_minutes * 60:
            self._cooldown[device_id] = time()
            return True
        return False
    
    def send(self, result: Dict):
        """Send alert if device went down"""
        if not result.get('status_changed'):
            return
        
        if result['transition_type'] in ['up_to_down', 'initial_down']:
            if not self._should_alert(result['device_id']):
                return
            
            subject = f"🔴 ALERT: {result['name']} is DOWN"
            body = f"""
Device: {result['name']} ({result['ip']})
Status: DOWN
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

The device has been unreachable for {result.get('fail_count', 0)} consecutive checks.

NetPulse Monitoring System
"""
            self._send_email(subject, body)
    
    def _send_email(self, subject: str, body: str):
        """Send email"""
        if not self.username or not self.password:
            print(f"⚠️  Email not configured. Would have sent: {subject}")
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.from_addr
            msg['To'] = ', '.join(self.to_addrs)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()
            print(f"📧 Alert sent: {subject}")
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
