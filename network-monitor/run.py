#!/usr/bin/env python3
"""
NetPulse - Simple Network Monitoring
Just add devices and let it run
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.device import Device
from app.core.monitor_engine import MonitoringEngine


def print_result(result):
    """Simple display"""
    status = result['current_status']
    icon = "🟢" if status == "UP" else "🔴" if status == "DOWN" else "⚪"
    latency = f"{result['latency_ms']:.1f}ms" if result.get('latency_ms') else "N/A"
    
    if result.get('status_changed'):
        if 'down' in result.get('transition_type', ''):
            print(f"\n⚠️  {icon} {result['name']} is now DOWN!")
        elif 'up' in result.get('transition_type', ''):
            print(f"\n✅ {icon} {result['name']} is back UP!")
    else:
        print(f"   {icon} {result['name']:20} - {status:6} (latency: {latency})")


def main():
    print("""
    ╔═══════════════════════════════════╗
    ║         NetPulse v1.0             ║
    ║    Simple Network Monitor         ║
    ╚═══════════════════════════════════╝
    """)
    
    engine = MonitoringEngine()
    
    # Add devices if none exist
    if not engine.get_devices():
        print("📝 No devices found. Let's add some:\n")
        
        while True:
            name = input("Device name (or press Enter to finish): ").strip()
            if not name:
                break
            ip = input(f"IP address for {name}: ").strip()
            retry = input("Retry count (how many failures before DOWN, default 2): ").strip()
            retry = int(retry) if retry else 2
            
            device_id = f"dev_{len(engine.get_devices())}"
            device = Device(device_id, name, ip, retry_count=retry)
            engine.add_device(device)
            print(f"✅ Added {name}\n")
    
    # Show current devices
    print("\n📋 Monitoring these devices:")
    for device in engine.get_devices():
        print(f"   • {device.name} ({device.ip_address}) - {device.retry_count} retries")
    
    # Start monitoring
    print("\n" + "="*50)
    interval = input("Check interval in seconds (default 30): ").strip()
    interval = int(interval) if interval else 30
    
    print("\n🚀 Starting NetPulse...")
    print("   Press Ctrl+C to stop\n")
    
    engine.monitor_forever(
        interval=interval,
        callback=print_result
    )


if __name__ == "__main__":
    main()
