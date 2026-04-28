#!/usr/bin/env python3
"""
Simple Monitoring Engine - With Parallel Execution
"""

import time
import subprocess
import re
from datetime import datetime
from typing import Dict, Optional, List
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.device import Device, DeviceStatus
from app.database.db import Database
from app.auth import UserAuth
from app.services.alert_v2 import AlertServiceV2


class MonitoringEngine:
    """Simple monitoring engine with parallel execution"""
    
    def __init__(self, db_path: str = "data/monitor.db", user_id: int = None, max_workers: int = 10):
        self.db = Database(db_path)
        self.devices: Dict[str, Device] = {}
        self.user_id = user_id
        self.max_workers = max_workers
        self._check_lock = threading.Lock()
        self.load_devices_from_db()
    
    def _handle_status_change_alert(self, device_id: str, old_status: str, new_status: str):
        """Handle status changes with the new event-driven alert system"""
        if old_status != new_status:
            try:
                alert_service = AlertServiceV2()
                alert_service.process_status_change(device_id, old_status, new_status)
            except Exception as e:
                print(f"⚠️ Alert error: {e}")
    
    def load_devices_from_db(self):
        """Load devices from database - tries user_devices first, then devices table"""
        devices_loaded = False
        
        if self.user_id:
            try:
                auth = UserAuth()
                user_devices = auth.get_user_devices(self.user_id)
                
                for device_data in user_devices:
                    # Remove device_group parameter as it's not in Device __init__
                    device = Device(
                        device_id=device_data['device_id'],
                        name=device_data['name'],
                        ip_address=device_data['ip_address'],
                        retry_count=device_data.get('retry_count', 2),
                        timeout=2
                    )
                    self.devices[device.device_id] = device
                
                if self.devices:
                    print(f"✅ Loaded {len(self.devices)} devices from user {self.user_id}")
                    devices_loaded = True
            except Exception as e:
                print(f"⚠️  Error loading user devices: {e}")
        
        if not devices_loaded:
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
            
            if self.devices:
                print(f"✅ Loaded {len(self.devices)} devices from global table")
            else:
                print(f"⚠️  No devices found.")
    
    def ping(self, ip: str, timeout: int = 2, count: int = 3) -> Dict:
        """
        Advanced ping with multiple packets for accuracy.
        Returns: {
            'is_reachable': bool,
            'latency_ms': float,  # average latency
            'min_latency_ms': float,
            'max_latency_ms': float,
            'packet_loss_percent': float,
            'jitter_ms': float
        }
        """
        latencies = []
        success_count = 0
        
        for attempt in range(count):
            try:
                if sys.platform == "win32":
                    cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
                else:
                    cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 1)
                
                if result.returncode == 0:
                    match = re.search(r'time[=<](\d+(?:\.\d+)?)\s*ms', result.stdout)
                    if match:
                        latencies.append(float(match.group(1)))
                        success_count += 1
            except subprocess.TimeoutExpired:
                continue
            except Exception as e:
                print(f"⚠️  Ping error for {ip}: {e}")
                continue
            
            if attempt < count - 1:
                time.sleep(0.2)
        
        # Calculate metrics
        packet_loss = ((count - success_count) / count) * 100.0
        
        result = {
            'is_reachable': success_count > 0,
            'latency_ms': None,
            'min_latency_ms': None,
            'max_latency_ms': None,
            'packet_loss_percent': packet_loss,
            'jitter_ms': None
        }
        
        if latencies:
            result['latency_ms'] = sum(latencies) / len(latencies)
            result['min_latency_ms'] = min(latencies)
            result['max_latency_ms'] = max(latencies)
            if len(latencies) > 1:
                import statistics
                result['jitter_ms'] = statistics.stdev(latencies)
        
        return result
    
    def check_single_device(self, device: Device) -> Dict:
        """Check a single device (thread-safe)"""
        try:
            ping_result = self.ping(device.ip_address, device.timeout, count=3)
            
            # Capture old status BEFORE processing the check
            old_status = device.status.value if device.status else "UNKNOWN"
            
            # Use average latency for state machine
            result = device.process_check(ping_result['is_reachable'], ping_result['latency_ms'])
            
            # Get new status after processing
            new_status = result['current_status']
            
            # Trigger alert if status changed
            if old_status != new_status:
                self._handle_status_change_alert(device.device_id, old_status, new_status)
            
            # Add detailed metrics to result
            result['ping_details'] = {
                'min_latency_ms': ping_result['min_latency_ms'],
                'max_latency_ms': ping_result['max_latency_ms'],
                'packet_loss_percent': ping_result['packet_loss_percent'],
                'jitter_ms': ping_result['jitter_ms']
            }
            
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
                        'latency_ms': ping_result['latency_ms']
                    })
            except Exception as e:
                print(f"⚠️  Database error: {e}")
            
            return result
            
        except Exception as e:
            print(f"❌ Error checking device {device.name}: {e}")
            return {
                'device_id': device.device_id,
                'name': device.name,
                'ip': device.ip_address,
                'timestamp': datetime.now(),
                'current_status': device.status.value,
                'status_changed': False,
                'error': str(e)
            }
    
    def check_all_devices(self) -> list:
        """Check all devices in parallel"""
        results = []
        
        print(f"🚀 Checking {len(self.devices)} devices in parallel (max {self.max_workers} workers)...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_device = {
                executor.submit(self.check_single_device, device): device
                for device in self.devices.values()
            }
            
            for future in as_completed(future_to_device):
                device = future_to_device[future]
                try:
                    result = future.result(timeout=10)
                    results.append(result)
                except Exception as e:
                    print(f"❌ Future failed for {device.name}: {e}")
                    results.append({
                        'device_id': device.device_id,
                        'name': device.name,
                        'ip': device.ip_address,
                        'timestamp': datetime.now(),
                        'current_status': device.status.value,
                        'status_changed': False,
                        'error': str(e)
                    })
        
        return results
    
    def monitor_forever(self, interval: int = 30, callback=None):
        """Run monitoring forever with parallel execution"""
        if not self.devices:
            print("❌ No devices configured.")
            return
        
        print(f"\n{'='*60}")
        print(f"🚀 NetPulse Monitoring Started")
        print(f"📊 Devices: {len(self.devices)}")
        print(f"⚡ Mode: PARALLEL (max {self.max_workers} workers)")
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
                
                # Check all devices in parallel
                results = self.check_all_devices()
                
                # Sort and display results
                results.sort(key=lambda x: x.get('name', ''))
                
                for result in results:
                    if callback:
                        callback(result)
                    
                    if result.get('status_changed'):
                        status = result['current_status']
                        name = result['name']
                        if status == "DOWN":
                            print(f"   ⚠️  {name} is now DOWN!")
                        elif status == "UP":
                            downtime = result.get('downtime_seconds', 0)
                            if downtime:
                                mins = int(downtime / 60)
                                secs = int(downtime % 60)
                                print(f"   ✅ {name} is back UP (was down for {mins}m {secs}s)")
                            else:
                                print(f"   ✅ {name} is now UP")
                
                elapsed = time.time() - start
                
                # Warn if cycle exceeded interval
                if elapsed > interval:
                    print(f"⚠️  Cycle exceeded interval by {elapsed - interval:.2f}s")
                else:
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
    
    def get_devices(self) -> list:
        """Get all devices"""
        return list(self.devices.values())