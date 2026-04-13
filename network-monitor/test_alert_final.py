#!/usr/bin/env python3
"""Test email alerts with aiosmtpd"""

import os
import sys

# Configure environment for local SMTP server
os.environ['SMTP_SERVER'] = 'localhost'
os.environ['SMTP_PORT'] = '1025'
os.environ['SMTP_USERNAME'] = 'test@localhost'
os.environ['SMTP_PASSWORD'] = 'anything-works-for-local'
os.environ['SMTP_TO'] = 'mmadubugwukingsley@gmail.com'
os.environ['SMTP_FROM'] = 'netpulse@localhost'

# Add current directory to path
sys.path.insert(0, '/home/kmtech/Projects/NetPulse/network-monitor')

# Try to import AlertService
try:
    # First try: from app.py (if it's in current directory)
    from app import AlertService
    print("✅ Imported AlertService from app.py")
except ImportError:
    try:
        # Second try: from services.alert module
        from services.alert import AlertService
        print("✅ Imported AlertService from services.alert")
    except ImportError:
        print("❌ Could not find AlertService. Searching...")
        import glob
        found = False
        for file in glob.glob('**/*.py', recursive=True):
            if 'app.py' in file or 'alert.py' in file:
                print(f"Checking: {file}")
                try:
                    # Try to dynamically import
                    spec = __import__('importlib.util')
                    module_name = file.replace('/', '.').replace('.py', '')
                    if module_name.startswith('.'):
                        module_name = module_name[1:]
                    module = __import__(module_name, fromlist=['AlertService'])
                    if hasattr(module, 'AlertService'):
                        AlertService = getattr(module, 'AlertService')
                        print(f"✅ Found AlertService in {file}")
                        found = True
                        break
                except:
                    pass
        if not found:
            print("❌ AlertService not found in any Python file")
            sys.exit(1)

# Create and test alert service
print("\n📧 Creating AlertService...")
alert = AlertService()

print("📨 Sending test alert...")
if alert.send_test_alert():
    print("✅ Test email sent successfully!")
    print("\n📝 Check the terminal running aiosmtpd - you should see the email content printed there")
else:
    print("❌ Failed to send test email")