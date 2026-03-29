#!/usr/bin/env python3
"""
NetPulse - Simple Network Monitor
Just add devices by name and IP - everything else has smart defaults
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.device import Device, DeviceStatus
from app.core.monitor_engine import MonitoringEngine


def print_result(result):
    """Display monitoring results"""
    status = result['current_status']
    
    if status == "UP":
        icon = "🟢"
    elif status == "DEGRADED":
        icon = "🟡"
    elif status == "DOWN":
        icon = "🔴"
    else:
        icon = "⚪"
    
    latency = f"{result['latency_ms']:.1f}ms" if result.get('latency_ms') else "N/A"
    
    quality_info = ""
    if result.get('packet_loss_percent', 0) > 0:
        quality_info += f" | loss: {result['packet_loss_percent']:.0f}%"
    if result.get('avg_latency_ms'):
        quality_info += f" | avg: {result['avg_latency_ms']:.0f}ms"
    
    duration = ""
    if status == "DEGRADED" and result.get('degraded_seconds'):
        secs = result['degraded_seconds']
        duration = f" ({secs:.0f}s)" if secs < 60 else f" ({secs/60:.1f}m)"
    elif status == "DOWN" and result.get('downtime_seconds'):
        secs = result['downtime_seconds']
        duration = f" ({secs:.0f}s)" if secs < 60 else f" ({secs/60:.1f}m)"
    
    if result.get('status_changed'):
        print(f"\n⚠️  {icon} {result['name']} is now {status}{duration}!")
        if result.get('transition_type') == 'up_to_degraded':
            print(f"   Performance: {quality_info.strip(' | ')}")
    else:
        print(f"   {icon} {result['name']:20} - {status:8} (latency: {latency:8}){quality_info}{duration}")


def list_devices(engine):
    """List all devices"""
    devices = engine.get_devices()
    if not devices:
        print("\n📭 No devices configured")
        return
    
    print("\n" + "="*70)
    print(f"{'Name':<25} {'IP Address':<20} {'Status':<10}")
    print("="*70)
    
    for device in devices:
        status = device.status.value if device.status else "UNKNOWN"
        icon = "🟢" if status == "UP" else "🟡" if status == "DEGRADED" else "🔴" if status == "DOWN" else "⚪"
        print(f"{icon} {device.name:<24} {device.ip_address:<20} {status:<10}")
    
    print("="*70)
    print("\n💡 Tip: Devices show DEGRADED if latency >200ms or packet loss >10%")


def add_device(engine):
    """Add a new device - just name and IP"""
    print("\n--- Add New Device ---")
    
    name = input("Device Name: ").strip()
    if not name:
        print("❌ Name cannot be empty!")
        return
    
    ip = input("IP Address: ").strip()
    if not ip:
        print("❌ IP address cannot be empty!")
        return
    
    # Generate a simple device ID
    device_id = name.lower().replace(' ', '_')
    
    # Use smart defaults that work for most networks
    device = Device(
        device_id=device_id,
        name=name,
        ip_address=ip,
        retry_count=2,           # Default: 2 failures before DOWN
        max_latency_ms=200.0,    # Default: >200ms = DEGRADED
        packet_loss_threshold=10.0  # Default: >10% loss = DEGRADED
    )
    
    if engine.add_device(device):
        print(f"\n✅ Added: {name} ({ip})")
        print(f"   • DOWN after 2 failures")
        print(f"   • DEGRADED if latency >200ms or packet loss >10%")
    else:
        print("❌ Failed to add device")


def update_device(engine):
    """Update device - just name and IP"""
    devices = engine.get_devices()
    if not devices:
        print("\n📭 No devices to update")
        return
    
    print("\n--- Update Device ---")
    for device in devices:
        status = device.status.value if device.status else "UNKNOWN"
        print(f"   {device.device_id}: {device.name} ({device.ip_address}) - {status}")
    
    device_id = input("\nDevice ID to update: ").strip()
    device = None
    for d in devices:
        if d.device_id == device_id:
            device = d
            break
    
    if not device:
        print(f"❌ Device '{device_id}' not found")
        return
    
    print(f"\nUpdating: {device.name} ({device.ip_address})")
    print("Leave blank to keep current value\n")
    
    name = input(f"Name [{device.name}]: ").strip()
    ip = input(f"IP Address [{device.ip_address}]: ").strip()
    
    updates = {}
    if name:
        updates['name'] = name
    if ip:
        updates['ip_address'] = ip
    
    if updates:
        if engine.update_device(device_id, **updates):
            print(f"\n✅ Device updated successfully!")
            # Show updated info
            updated = next((d for d in engine.get_devices() if d.device_id == device_id), None)
            if updated:
                print(f"   Now: {updated.name} ({updated.ip_address})")
        else:
            print("❌ Failed to update device")
    else:
        print("No changes made")


def delete_device(engine):
    """Delete a device"""
    devices = engine.get_devices()
    if not devices:
        print("\n📭 No devices to delete")
        return
    
    print("\n--- Delete Device ---")
    for device in devices:
        print(f"   {device.device_id}: {device.name} ({device.ip_address})")
    
    device_id = input("\nDevice ID to delete: ").strip()
    
    device = next((d for d in devices if d.device_id == device_id), None)
    if device:
        confirm = input(f"Delete {device.name} ({device.ip_address})? (y/n): ").strip().lower()
        if confirm == 'y':
            if engine.remove_device(device_id):
                print(f"✅ Device '{device.name}' deleted")
            else:
                print("❌ Failed to delete device")
        else:
            print("Cancelled")
    else:
        print(f"❌ Device '{device_id}' not found")


def show_help():
    """Show help"""
    print("""
    📖 NetPulse Help
    
    Simple Network Monitoring:
    • 🟢 UP = Device is reachable with good performance
    • 🟡 DEGRADED = Device is reachable but slow (>200ms latency or >10% packet loss)
    • 🔴 DOWN = Device is unreachable after 2 failures
    
    Default Thresholds (work for most networks):
    • DOWN after 2 consecutive failures
    • DEGRADED if latency >200ms or packet loss >10%
    
    To adjust thresholds for your network (optional):
    sqlite3 data/monitor.db "UPDATE devices SET max_latency_ms=300 WHERE device_id='gw1';"
    """)


def main():
    print("""
    ╔═══════════════════════════════════════╗
    ║         NetPulse v1.0                 ║
    ║    Simple Network Monitor             ║
    ║    Just add name and IP               ║
    ╚═══════════════════════════════════════╝
    """)
    
    engine = MonitoringEngine()
    
    # Show initial device list
    devices = engine.get_devices()
    if devices:
        print(f"✅ Monitoring {len(devices)} devices:\n")
        for device in devices:
            print(f"   • {device.name} ({device.ip_address})")
    
    while True:
        print("\n" + "="*50)
        print("NetPulse - Main Menu")
        print("="*50)
        print("1. 📋 List devices")
        print("2. ➕ Add device")
        print("3. ✏️  Update device")
        print("4. 🗑️  Delete device")
        print("5. 🚀 Start monitoring")
        print("6. 📖 Help")
        print("7. 🚪 Exit")
        print("="*50)
        
        choice = input("Select option (1-7): ").strip()
        
        if choice == '1':
            list_devices(engine)
        elif choice == '2':
            add_device(engine)
        elif choice == '3':
            update_device(engine)
        elif choice == '4':
            delete_device(engine)
        elif choice == '5':
            interval = input("\nCheck interval in seconds (default 30): ").strip()
            interval = int(interval) if interval else 30
            
            print("\n🚀 Starting NetPulse monitoring...")
            print("   🟢 UP = Normal")
            print("   🟡 DEGRADED = High latency (>200ms) or packet loss (>10%)")
            print("   🔴 DOWN = Unreachable after 2 failures")
            print("   Press Ctrl+C to return to menu\n")
            
            engine.monitor_forever(
                interval=interval,
                callback=print_result
            )
        elif choice == '6':
            show_help()
        elif choice == '7':
            print("\n👋 Goodbye from NetPulse!")
            break
        else:
            print("❌ Invalid option. Choose 1-7")


if __name__ == "__main__":
    main()
