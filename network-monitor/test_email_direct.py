#!/usr/bin/env python3
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Get SMTP settings
smtp_server = os.getenv('SMTP_SERVER')
smtp_port = int(os.getenv('SMTP_PORT', 587))
username = os.getenv('SMTP_USERNAME')
password = os.getenv('SMTP_PASSWORD')
from_addr = os.getenv('SMTP_FROM')
to_addr = os.getenv('SMTP_TO')

print(f"Testing SMTP Configuration")
print(f"Server: {smtp_server}:{smtp_port}")
print(f"From: {from_addr}")
print(f"To: {to_addr}")
print(f"Username: {username}")
print(f"Password: {'*' * len(password) if password else 'NOT SET'}")

if not all([smtp_server, username, password, to_addr]):
    print("\n❌ Missing SMTP configuration!")
    exit(1)

try:
    # Create message
    msg = MIMEMultipart()
    msg['From'] = from_addr or username
    msg['To'] = to_addr
    msg['Subject'] = "NetPulse Test - Direct SMTP"

    body = "This is a test email from NetPulse to verify SMTP configuration."
    msg.attach(MIMEText(body, 'plain'))

    # Send email
    print("\n📧 Connecting to SMTP server...")
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    print("📧 Logging in...")
    server.login(username, password)
    print("📧 Sending email...")
    server.send_message(msg)
    server.quit()
    
    print("\n✅ Email sent successfully! Check your inbox.")
    
except Exception as e:
    print(f"\n❌ Failed to send email: {e}")
    print("\nTroubleshooting tips:")
    print("1. If using Gmail, make sure you're using an App Password")
    print("2. Go to: https://myaccount.google.com/apppasswords")
    print("3. Generate a new password and update .env")
    print("4. Restart the API server after updating")

