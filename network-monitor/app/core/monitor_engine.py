#!/usr/bin/env python3
"""
Simple Monitoring Engine
"""

import time
import subprocess
import re
from datetime import datetime
from typing import Dict, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.device import Device, DeviceStatus
from app.database.db import Database


class MonitoringEngine:
    """Simple monitoring engine"""
    
    def __init__(self, db_path: str = "data/monitor.db"):
        self.db = Database(db_path)
        self.devices: Dict[str, Device] = {}
        self.load_devices_from_db()
    
    def load_devices_from_db(self):
        """Load all devices from database"""
        devices_data = self.db.get_all_devices()
        
        for device_data in devices_data:
            device = Device(
                device_id=device_data['device_id'],
                name=device_data['name'],
                ip_address=device_data['ip_address'],
                retry_count=device_data['retry_count'],
                timeout=device_data['timeout']
            )
            self.devices[device.device_id] = device
        
        print(f"✅ Loaded {len(self.devices)} devices")
    
    def ping(self, ip: str, timeout: int = 2) -> tuple:
        """Simple ping - returns (is_reachable, latency_ms)"""
        try:
            if sys.platform == "win32":
                cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
            else:
                cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 1)
            
            if result.returncode == 0:
                match = re.search(r'time[=<](\d+(?:\.\d+)?)\s*ms', result.stdout)
                if match:
                    return True, float(match.group(1))
                return True, 0.0
            return False, None
        except:
            return False, None
    
    def check_device(self, device: Device) -> Dict:
        """Check a single device"""
        is_reachable, latency = self.ping(device.ip_address, device.timeout)
        result = device.process_check(is_reachable, latency)
        
        # Log to database
        try:
            self.db.add_log(result)
            if result.get('status_changed'):
                self.db.add_state_change({
                    'device_id': device.device_id,
                    'timestamp': result['timestamp'],
                    'from_status': result.get('previous_status'),
                    'to_status': result['current_status'],
                    'transition_type': result.get('transition_type'),
                    'latency_ms': latency
                })
        except Exception as e:
            print(f"⚠️  Database error: {e}")
        
        return result
    
    def check_all_devices(self) -> list:
        """Check all devices"""
        results = []
        for device in self.devices.values():
            results.append(self.check_device(device))
        return results
    
    def monitor_forever(self, interval: int = 30, callback=None):
        """Run monitoring forever"""
        if not self.devices:
            print("❌ No devices configured")
            return
        
        print(f"\n{'='*60}")
        print(f"🚀 NetPulse Monitoring Started")
        print(f"📊 Devices: {len(self.devices)}")
        print(f"⏱️  Check interval: {interval} seconds")
        print(f"⌨️  Press Ctrl+C to stop")
        print(f"{'='*60}\n")
        
        cycle = 0
        try:
            while True:
                cycle += 1
                start = time.time()
                print(f"\n📡 Cycle #{cycle} @ {datetime.now().strftime('%H:%M:%S')}")
                print("-" * 40)
                
                for device in self.devices.values():
                    result = self.check_device(device)
                    if callback:
                        callback(result)
                
                elapsed = time.time() - start
                print(f"⏱️  Cycle completed in {elapsed:.1f}s")
                
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            print(f"\n\n✅ Monitoring stopped")
            self._show_summary()
    
    def _show_summary(self):
        """Show final status"""
        print("\n📊 Final Status:")
        for device in self.devices.values():
            icon = "🟢" if device.status == DeviceStatus.UP else "🔴" if device.status == DeviceStatus.DOWN else "🟡"
            print(f"{icon} {device.name}: {device.status.value}")
    
    def add_device(self, device: Device) -> bool:
        """Add device to monitoring"""
        if device.device_id in self.devices:
            return False
        if self.db.add_device(**device.to_dict()):
            self.devices[device.device_id] = device
            return True
        return False
    
    def remove_device(self, device_id: str) -> bool:
        """Remove device from monitoring"""
        if device_id not in self.devices:
            return False
        if self.db.delete_device(device_id):
            del self.devices[device_id]
            return True
        return False
    
    def update_device(self, device_id: str, **kwargs) -> bool:
        """Update device properties"""
        if device_id not in self.devices:
            return False
        device = self.devices[device_id]
        for key, value in kwargs.items():
            if hasattr(device, key):
                setattr(device, key, value)
        return self.db.update_device(device_id, **kwargs)
    
    def get_devices(self) -> list:
        """Get all devices"""
        return list(self.devices.values())
