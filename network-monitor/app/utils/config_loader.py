"""Configuration loader for NetPulse"""
import os
from pathlib import Path
from typing import Optional

def load_env_file(env_path: Optional[str] = None) -> None:
    """Load environment variables from .env file"""
    if env_path is None:
        env_path = Path(__file__).parent.parent.parent / '.env'
    
    if not Path(env_path).exists():
        print(f"⚠️  No .env file found at {env_path}")
        return
    
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()
    
    print(f"✅ Loaded configuration from {env_path}")

def get_smtp_config() -> dict:
    """Get SMTP configuration from environment"""
    return {
        'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', '587')),
        'username': os.getenv('SMTP_USERNAME', ''),
        'password': os.getenv('SMTP_PASSWORD', ''),
        'from_addr': os.getenv('SMTP_FROM', ''),
        'to_addrs': [addr.strip() for addr in os.getenv('SMTP_TO', '').split(',') if addr.strip()],
        'alerts_enabled': os.getenv('ALERTS_ENABLED', 'true').lower() == 'true'
    }

def get_alert_settings() -> dict:
    """Get alert configuration from environment"""
    return {
        'down_cooldown': int(os.getenv('ALERT_DOWN_COOLDOWN', '5')),
        'degraded_cooldown': int(os.getenv('ALERT_DEGRADED_COOLDOWN', '15')),
        'recovery_cooldown': int(os.getenv('ALERT_RECOVERY_COOLDOWN', '5')),
        'alert_on_down': os.getenv('ALERT_ON_DOWN', 'true').lower() == 'true',
        'alert_on_degraded': os.getenv('ALERT_ON_DEGRADED', 'true').lower() == 'true',
        'alert_on_recovery': os.getenv('ALERT_ON_RECOVERY', 'true').lower() == 'true',
        'down_success_rate_threshold': float(os.getenv('DOWN_SUCCESS_RATE_THRESHOLD', '30.0')),
        'down_packet_loss_threshold': float(os.getenv('DOWN_PACKET_LOSS_THRESHOLD', '50.0'))
    }
