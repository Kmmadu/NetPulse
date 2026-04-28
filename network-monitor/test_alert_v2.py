#!/usr/bin/env python3
"""Test the new alert system V2"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.alert_v2 import AlertServiceV2

def test():
    print("\n" + "="*60)
    print("Testing Alert Service V2")
    print("="*60)
    
    alert = AlertServiceV2()
    
    print("\n📧 Sending test email...")
    if alert.send_test_alert():
        print("✅ Test email sent successfully!")
        print("   Check your inbox")
    else:
        print("❌ Failed to send test email")
        print("   Check SMTP configuration in .env file")

if __name__ == "__main__":
    test()
