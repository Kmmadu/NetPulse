#!/usr/bin/env python3
"""
NetPulse CLI - Command Line Interface for Network Monitoring
"""

import sys
import os
import time
from datetime import datetime
from typing import List, Optional

# Add parent directory to path for imports - dynamic path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.device import Device, DeviceStatus


class DeviceCLI:
    """Command-line interface for device management"""
    
    def __init__(self):
        """Initialize CLI with device manager"""
        self.devices = {}  # Simple dict for now, will be replaced with DB
        self.running = False
        
    def add_device_interactive(self):
        """Interactive device addition"""
        print("\n--- Add New Device ---")
        device_id = input("Device ID (unique, no spaces): ").strip()
        
        if not device_id:
            print("❌ Device ID cannot be empty")
            return
        
        if device_id in self.devices:
            print(f"❌ Device ID '{device_id}' already exists")
            return
        
        name = input("Display Name: ").strip()
        if not name:
            print("❌ Name cannot be empty")
            return
        
        ip = input("IP Address: ").strip()
        if not self._validate_ip(ip):
            print("❌ Invalid IP address format")
            return
        
        retry = input("Retry count (default 2, min 1): ").strip()
        retry = int(retry) if retry else 2
        
        # Optional quality thresholds
        use_quality = input("Enable quality monitoring? (y/n, default y): ").strip().lower()
        if use_quality != 'n':
            max_latency = input("Max latency before degraded (ms, default 100): ").strip()
            max_latency = float(max_latency) if max_latency else 100.0
            critical_latency = input("Critical latency threshold (ms, default 500): ").strip()
            critical_latency = float(critical_latency) if critical_latency else 500.0
            
            from app.models.device import QualityThresholds
            thresholds = QualityThresholds(
                max_latency_ms=max_latency,
                critical_latency_ms=critical_latency
            )
            device = Device(device_id, name, ip, retry_count=retry, 
                          quality_thresholds=thresholds)
        else:
            device = Device(device_id, name, ip, retry_count=retry)
        
        self.devices[device_id] = device
        print(f"✅ Added device: {name} ({ip})")
    
    def _validate_ip(self, ip: str) -> bool:
        """Basic IP validation"""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not part.isdigit():
                    return False
                num = int(part)
                if num < 0 or num > 255:
                    return False
            return True
        except:
            return False
    
    def list_devices(self):
        """Display all devices with current status"""
        if not self.devices:
            print("\n📭 No devices configured")
            return
        
        print("\n" + "="*100)
        print(f"{'ID':<15} {'Name':<20} {'IP Address':<15} {'Retries':<8} {'Status':<12} {'Fails':<8} {'Quality':<8}")
        print("="*100)
        
        for device in self.devices.values():
            # Status icons (CLI only)
            if device.status == DeviceStatus.UP:
                status_icon = "🟢"
            elif device.status == DeviceStatus.DEGRADED:
                status_icon = "🟡"
            elif device.status == DeviceStatus.DOWN:
                status_icon = "🔴"
            else:
                status_icon = "⚪"
            
            fails_display = f"{device.fail_count}/{device.retry_count}"
            quality_display = f"{device.quality_score:.0f}%" if device.quality_score else "N/A"
            
            print(f"{device.device_id:<15} {device.name:<20} {device.ip_address:<15} "
                  f"{device.retry_count:<8} {status_icon} {device.status_text:<10} "
                  f"{fails_display:<8} {quality_display:<8}")
        
        print("="*100)
        
        # Summary
        up = sum(1 for d in self.devices.values() if d.status == DeviceStatus.UP)
        degraded = sum(1 for d in self.devices.values() if d.status == DeviceStatus.DEGRADED)
        down = sum(1 for d in self.devices.values() if d.status == DeviceStatus.DOWN)
        unknown = sum(1 for d in self.devices.values() if d.status == DeviceStatus.UNKNOWN)
        
        print(f"\n📊 Summary: 🟢 {up} UP | 🟡 {degraded} DEGRADED | 🔴 {down} DOWN | ⚪ {unknown} UNKNOWN")
    
    def remove_device(self):
        """Remove a device interactively"""
        if not self.devices:
            print("\n📭 No devices to remove")
            return
        
        self.list_devices()
        device_id = input("\nDevice ID to remove: ").strip()
        
        if device_id in self.devices:
            removed = self.devices.pop(device_id)
            print(f"🗑️  Removed device: {removed.name} ({removed.ip_address})")
        else:
            print(f"❌ Device ID '{device_id}' not found")
    
    def simulate_ping(self, ip: str) -> tuple:
        """Simulate ping for testing (will be replaced with real ping)"""
        import random
        
        # Simulate realistic network conditions
        # 85% success rate, with occasional high latency
        rand = random.random()
        
        if rand < 0.85:  # 85% success
            # Latency varies: 5-150ms normally, sometimes high
            if rand < 0.05:  # 5% chance of high latency
                latency = random.uniform(150, 500)
            else:
                latency = random.uniform(5, 100)
            return True, latency
        else:
            return False, None
    
    def monitor_continuous(self, interval: int = 5):
        """Continuous monitoring loop with quality metrics"""
        if not self.devices:
            print("\n❌ No devices to monitor. Add devices first.")
            return
        
        print(f"\n{'='*70}")
        print(f"🚀 NetPulse Monitoring Started")
        print(f"📊 Devices monitored: {len(self.devices)}")
        print(f"⏱️  Check interval: {interval} seconds")
        print(f"⌨️  Press Ctrl+C to stop")
        print(f"{'='*70}\n")
        
        self.running = True
        cycle = 0
        
        try:
            while self.running:
                cycle += 1
                print(f"\n📡 Cycle #{cycle} @ {datetime.now().strftime('%H:%M:%S')}")
                print("-" * 50)
                
                # Check each device
                for device in self.devices.values():
                    # Simulate ping (will be replaced with real ping service)
                    is_up, latency = self.simulate_ping(device.ip_address)
                    
                    # Process result
                    result = device.process_check_result(is_up, latency)
                    
                    # Display result
                    self._display_check_result(result)
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print(f"\n\n{'='*70}")
            print("⏹️  Monitoring stopped by user")
            self._display_final_summary()
            print(f"{'='*70}")
            self.running = False
    
    def _display_check_result(self, result: dict):
        """Display a single check result with quality metrics"""
        timestamp = result['timestamp'].strftime('%H:%M:%S')
        status = result['current_status']
        
        # Status icons (CLI only)
        if status == "UP":
            status_icon = "🟢"
        elif status == "DEGRADED":
            status_icon = "🟡"
        elif status == "DOWN":
            status_icon = "🔴"
        else:
            status_icon = "⚪"
        
        latency_str = f"{result['latency_ms']:.1f}ms" if result['latency_ms'] else "N/A"
        
        # Show quality info if available
        quality_info = ""
        if result.get('quality') and result['quality'].get('quality_score'):
            score = result['quality']['quality_score']
            quality_info = f" | Quality: {score:.0f}%"
        
        # Highlight status changes
        if result['status_changed']:
            print(f"\n⚠️  {status_icon} [{timestamp}] {result['name']:20} ({result['ip']})")
            if result['transition_type'] == 'up_to_degraded':
                print(f"   ⚠️  Device is now DEGRADED (performance issues){quality_info}")
                if result.get('quality', {}).get('issues'):
                    print(f"   Issues: {', '.join(result['quality']['issues'][:2])}")
            elif result['transition_type'] == 'degraded_to_up':
                print(f"   ✅ Device recovered to UP{quality_info}")
            elif result['transition_type'] == 'up_to_down':
                print(f"   ❌ Device is now DOWN (unreachable)")
            elif result['transition_type'] == 'degraded_to_down':
                print(f"   ❌ Device is now DOWN (from degraded state)")
            elif result['transition_type'] == 'down_to_up':
                print(f"   ✅ Device is now UP{quality_info}")
            elif result['transition_type'] == 'down_to_degraded':
                print(f"   ⚠️  Device is now DEGRADED (recovering){quality_info}")
            elif result['transition_type'] == 'initial_up':
                print(f"   ✅ Device is UP{quality_info}")
            elif result['transition_type'] == 'initial_degraded':
                print(f"   ⚠️  Device is DEGRADED{quality_info}")
                if result.get('quality', {}).get('issues'):
                    print(f"   Issues: {', '.join(result['quality']['issues'][:2])}")
            elif result['transition_type'] == 'initial_down':
                print(f"   ❌ Device is DOWN (initial detection)")
            else:
                print(f"   Status changed to {status}")
        else:
            # Normal status display
            print(f"   {status_icon} [{timestamp}] {result['name']:20} "
                  f"- {status:8} (latency: {latency_str:8} | fails: {result['fail_count']}/{result['retry_count']}{quality_info})")
    
    def _display_final_summary(self):
        """Display final status summary"""
        print("\n📊 Final Status Summary:")
        print("-" * 60)
        
        for device in self.devices.values():
            if device.status == DeviceStatus.UP:
                icon = "🟢"
            elif device.status == DeviceStatus.DEGRADED:
                icon = "🟡"
            elif device.status == DeviceStatus.DOWN:
                icon = "🔴"
            else:
                icon = "⚪"
            
            quality_str = f" (Q:{device.quality_score:.0f}%)" if device.quality_score else ""
            print(f"{icon} {device.name:20} ({device.ip_address:15}) - {device.status_text}{quality_str}")
    
    def run(self):
        """Main CLI loop"""
        while True:
            print("\n" + "="*50)
            print("🌐 NetPulse - Network Monitoring System")
            print("="*50)
            print("1. 📋 List all devices")
            print("2. ➕ Add device")
            print("3. 🗑️  Remove device")
            print("4. 🚀 Start monitoring")
            print("5. 🚪 Exit")
            print("="*50)
            
            choice = input("Select option (1-5): ").strip()
            
            if choice == '1':
                self.list_devices()
            elif choice == '2':
                self.add_device_interactive()
            elif choice == '3':
                self.remove_device()
            elif choice == '4':
                interval = input("Check interval in seconds (default 5): ").strip()
                interval = int(interval) if interval else 5
                self.monitor_continuous(interval)
            elif choice == '5':
                print("\n👋 Goodbye from NetPulse!")
                break
            else:
                print("❌ Invalid option")


def main():
    """Main entry point"""
    cli = DeviceCLI()
    
    # Add some test devices for demonstration
    if not cli.devices:
        print("\n📝 Adding example devices...")
        from app.models.device import QualityThresholds
        
        # Gateway with good thresholds
        cli.devices['gw1'] = Device('gw1', 'Gateway', '10.3.104.2', retry_count=2)
        
        # Google DNS with lower thresholds (more sensitive)
        cli.devices['dns1'] = Device('dns1', 'Google DNS', '8.8.8.8', retry_count=1)
        
        # Airtel with custom thresholds for degraded detection
        thresholds = QualityThresholds(
            max_latency_ms=50.0,
            critical_latency_ms=200.0,
            max_jitter_ms=20.0,
            packet_loss_threshold=5.0
        )
        cli.devices['airtel1'] = Device('airtel1', 'Airtel Ikeja', '10.2.104.6', 
                                        retry_count=1, quality_thresholds=thresholds)
    
    cli.run()


if __name__ == "__main__":
    main()
