#!/usr/bin/env python3
"""Test email alert configuration"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Try to load config loader if it exists, otherwise use direct approach
try:
    from app.utils.config_loader import load_env_file, get_smtp_config
    from app.services.alert import AlertService
    
    # Load environment variables
    load_env_file()
    
    # Get SMTP config
    config = get_smtp_config()
except ImportError:
    # Fallback: load .env manually
    print("Loading configuration from .env file...")
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    from app.services.alert import AlertService
    
    config = {
        'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', '587')),
        'username': os.getenv('SMTP_USERNAME', ''),
        'password': os.getenv('SMTP_PASSWORD', ''),
        'from_addr': os.getenv('SMTP_FROM', ''),
        'to_addrs': [addr.strip() for addr in os.getenv('SMTP_TO', '').split(',') if addr.strip()],
        'alerts_enabled': os.getenv('ALERTS_ENABLED', 'true').lower() == 'true'
    }

def main():
    print("\n" + "="*60)
    print("📧 NetPulse Email Configuration Test")
    print("="*60)
    print(f"\n📡 SMTP Server: {config['smtp_server']}")
    print(f"🔌 Port: {config['smtp_port']}")
    print(f"👤 Username: {config['username']}")
    print(f"📤 From: {config['from_addr']}")
    print(f"📬 To: {', '.join(config['to_addrs'])}")
    print(f"✅ Alerts Enabled: {config['alerts_enabled']}")
    
    if not config['alerts_enabled']:
        print("\n❌ Alerts are disabled. Set ALERTS_ENABLED=true in .env")
        return
    
    if not config['username'] or not config['password']:
        print("\n❌ Missing SMTP credentials. Please check SMTP_USERNAME and SMTP_PASSWORD in .env")
        return
    
    if not config['to_addrs']:
        print("\n❌ No recipient email. Please set SMTP_TO in .env")
        return
    
    # Initialize alert service
    print("\n🔧 Initializing alert service...")
    alert_service = AlertService(
        smtp_server=config['smtp_server'],
        smtp_port=config['smtp_port'],
        username=config['username'],
        password=config['password'],
        from_addr=config['from_addr'],
        to_addrs=config['to_addrs']
    )
    
    # Send test alert
    print("\n📧 Sending test email...")
    if alert_service.send_test_alert():
        print("\n✅ Test email sent successfully!")
        print(f"📬 Check inbox at: {', '.join(config['to_addrs'])}")
        print("⚠️  Note: Check spam folder if you don't see it in inbox")
    else:
        print("\n❌ Failed to send test email")
        print("\n🔧 Troubleshooting tips:")
        print("   1. Verify your app password is correct (no spaces)")
        print("   2. Check that 2FA is enabled on your Gmail account")
        print("   3. Make sure 'Less secure app access' is OFF (use App Password instead)")
        print("   4. Check your internet connection")
        print("   5. Try using a different SMTP server")

if __name__ == "__main__":
    main()
