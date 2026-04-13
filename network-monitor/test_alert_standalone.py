#!/usr/bin/env python3
"""Standalone test for AlertService - no imports needed"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class QuickAlertTest:
    def __init__(self, smtp_server, smtp_port, username, password, from_addr, to_addrs):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs if isinstance(to_addrs, list) else [to_addrs]
    
    def send_test(self):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.from_addr
            msg['To'] = ', '.join(self.to_addrs)
            msg['Subject'] = "[NetPulse] Test Alert"
            
            body = "This is a test email from NetPulse!"
            msg.attach(MIMEText(body, 'plain'))
            
            print(f"Connecting to {self.smtp_server}:{self.smtp_port}...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            print(f"Logging in as {self.username}...")
            server.login(self.username, self.password)
            print("Sending email...")
            server.send_message(msg)
            server.quit()
            
            print("✅ Email sent successfully!")
            return True
        except Exception as e:
            print(f"❌ Failed: {e}")
            return False

# Test with a local SMTP server (no credentials needed)
print("\n=== Testing with Local SMTP Server ===")
print("First, in another terminal, run: python -m smtpd -n -c DebuggingServer localhost:1025")
response = input("Have you started the local SMTP server? (y/n): ")

if response.lower() == 'y':
    test = QuickAlertTest(
        smtp_server='localhost',
        smtp_port=1025,
        username='',
        password='',
        from_addr='test@localhost',
        to_addrs='test@localhost'
    )
    test.send_test()

# Test with Gmail (requires real credentials)
print("\n=== Testing with Gmail (optional) ===")
use_gmail = input("Do you want to test with Gmail? (y/n): ")

if use_gmail.lower() == 'y':
    gmail_user = input("Gmail address: ")
    gmail_password = input("App password (not regular password): ")
    recipient = input("Recipient email: ")
    
    test = QuickAlertTest(
        smtp_server='smtp.gmail.com',
        smtp_port=587,
        username=gmail_user,
        password=gmail_password,
        from_addr=gmail_user,
        to_addrs=recipient
    )
    test.send_test()