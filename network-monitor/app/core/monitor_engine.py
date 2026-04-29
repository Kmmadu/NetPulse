#!/usr/bin/env python3
"""
Simple Monitoring Engine - With Parallel Execution
"""

import time
import subprocess
import re
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, Optional, List
import sys
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
        self.db_path = db_path
        self.devices: Dict[str, Device] = {}
        self.user_id = user_id
        self.max_workers = max_workers
        self._check_lock = threading.Lock()
        self.load_devices_from_db()
        
        # Alert state tracking to prevent duplicates and spam
        self._last_alert_state: Dict[str, str] = {}      # device_id -> last alerted status (UP/DOWN/DEGRADED)
        self._last_alert_time: Dict[str, float] = {}     # device_id -> timestamp of last alert
        self.alert_cooldown = 600  # 10 minutes cooldown in seconds
        
        # Track initial alerts sent on startup
        self._initial_alert_sent: Dict[str, bool] = {}
        self._load_initial_alert_state()
        self._ensure_initial_alert_column()
        
        # Run initial state check BEFORE normal monitoring starts
        self._run_initial_state_check()
    
    def _ensure_initial_alert_column(self):
        """Ensure devices table has initial_alert_sent column"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(devices)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'initial_alert_sent' not in columns:
                    cursor.execute("ALTER TABLE devices ADD COLUMN initial_alert_sent INTEGER DEFAULT 0")
                    print("✅ Added initial_alert_sent column to devices table")
        except Exception as e:
            print(f"⚠️ Failed to add initial_alert_sent column: {e}")
    
    def _get_alert_state_file_path(self) -> str:
        """Get path to the alert state persistence file"""
        return f"data/alert_state_user_{self.user_id}.json" if self.user_id else "data/alert_state.json"
    
    def _load_initial_alert_state(self):
        """Load persisted alert state to avoid duplicate alerts across restarts"""
        state_file = self._get_alert_state_file_path()
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
                    self._initial_alert_sent = data.get('initial_alerts', {})
                    self._last_alert_state = data.get('last_alert_state', {})
                    self._last_alert_time = data.get('last_alert_time', {})
                print(f"📂 Loaded alert state from {state_file}")
            except Exception as e:
                print(f"⚠️ Failed to load alert state: {e}")
    
    def _save_alert_state(self):
        """Persist alert state to survive restarts"""
        state_file = self._get_alert_state_file_path()
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, 'w') as f:
                json.dump({
                    'initial_alerts': self._initial_alert_sent,
                    'last_alert_state': self._last_alert_state,
                    'last_alert_time': self._last_alert_time,
                    'saved_at': datetime.now().isoformat()
                }, f)
        except Exception as e:
            print(f"⚠️ Failed to save alert state: {e}")
    
    def _run_initial_state_check(self):
        """
        Run a single initial check to evaluate device states on startup.
        This bypasses stability checks to detect DOWN devices immediately.
        """
        if not self.devices:
            print("⚠️ No devices to check during initial state")
            return
        
        print("\n" + "="*60)
        print("🔍 INITIAL STATE CHECK - Evaluating device status")
        print("="*60)
        
        for device_id, device in self.devices.items():
            # Skip if initial alert already sent (from previous run)
            if self._initial_alert_sent.get(device_id, False):
                continue
            
            # Check if device has already been alerted in database
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT initial_alert_sent FROM devices WHERE device_id = ?", (device_id,))
                    row = cursor.fetchone()
                    if row and row[0] == 1:
                        self._initial_alert_sent[device_id] = True
                        continue
            except Exception as e:
                print(f"⚠️ Failed to check initial_alert_sent for {device_id}: {e}")
            
            print(f"\n📡 Checking device: {device.name} ({device.ip_address})")
            
            # Perform ping check
            ping_result = self.ping(device.ip_address, device.timeout, count=3)
            
            # Process with initial check flag = True (bypasses stability)
            result = device.process_check(
                ping_result['is_reachable'],
                ping_result['latency_ms'],
                is_initial_check=True
            )
            
            # If device is DOWN, this will trigger an alert
            if result.get('status_changed') and result['current_status'] == 'DOWN':
                print(f"⚠️ Device {device.name} is DOWN - sending initial alert")
                
                # Send alert through normal flow
                self._handle_status_change_alert(
                    device_id=device_id,
                    old_status=result.get('previous_status', 'UNKNOWN'),
                    new_status=result['current_status'],
                    is_reachable=ping_result['is_reachable']
                )
                
                # Mark as alerted in database
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE devices SET initial_alert_sent = 1 WHERE device_id = ?", (device_id,))
                except Exception as e:
                    print(f"⚠️ Failed to update initial_alert_sent: {e}")
            elif result['current_status'] == 'UP':
                print(f"✅ Device {device.name} is UP")
            elif result['current_status'] == 'DEGRADED':
                print(f"⚠️ Device {device.name} is DEGRADED (no initial alert)")
            
            # Mark as processed
            self._initial_alert_sent[device_id] = True
            
            # Small delay between initial checks to avoid overwhelming
            time.sleep(0.5)
        
        # Save state after processing
        self._save_alert_state()
        print("\n" + "="*60)
        print("✅ INITIAL STATE CHECK COMPLETE")
        print("="*60 + "\n")
    
    def _handle_status_change_alert(self, device_id: str, old_status: str, new_status: str, 
                                     is_reachable: bool = None):
        """
        Handle status changes with the improved alert system.
        Passes is_reachable for false positive prevention.
        """
        current_time = time.time()
        
        # Check cooldown: if same state was alerted recently, skip
        last_state = self._last_alert_state.get(device_id)
        last_time = self._last_alert_time.get(device_id, 0)
        
        # Skip if same state and within cooldown period
        if last_state == new_status and (current_time - last_time) < self.alert_cooldown:
            device_name = device_id
            for dev in self.devices.values():
                if dev.device_id == device_id:
                    device_name = dev.name
                    break
            print(f"⏱️  Cooldown: Skipping duplicate {new_status} alert for {device_name}")
            return
        
        if old_status != new_status:
            try:
                alert_service = AlertServiceV2()
                alert_service.process_status_change(device_id, old_status, new_status, is_reachable)
                
                # ============================================================
                # CRITICAL: Sync database state with in-memory state
                # This ensures down_since is persisted across restarts
                # ============================================================
                for dev in self.devices.values():
                    if dev.device_id == device_id:
                        down_since = dev._down_since if new_status == "DOWN" else None
                        self.db.sync_device_state(device_id, new_status, down_since)
                        break
                
                # Update tracking after successful alert
                self._last_alert_state[device_id] = new_status
                self._last_alert_time[device_id] = current_time
                
                # Save state after each alert
                self._save_alert_state()
                
                device_name = device_id
                for dev in self.devices.values():
                    if dev.device_id == device_id:
                        device_name = dev.name
                        break
                print(f"🔔 Alert sent: {device_name} - {old_status} → {new_status}")
                
            except Exception as e:
                print(f"⚠️ Alert error for {device_id}: {e}")
    
    def load_devices_from_db(self):
        """Load devices from database - tries user_devices first, then devices table"""
        devices_loaded = False
        
        if self.user_id:
            try:
                auth = UserAuth()
                user_devices = auth.get_user_devices(self.user_id)
                
                for device_data in user_devices:
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
            'latency_ms': float,
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
            
            # Capture before status for debugging
            before_status = device.status.value if device.status else "UNKNOWN"
            
            # Normal check (not initial) - stability logic applies
            result = device.process_check(ping_result['is_reachable'], ping_result['latency_ms'])
            
            after_status = result['current_status']
            
            # Log status changes for debugging
            if before_status != after_status:
                print(f"[STATUS_CHANGE] {device.name}: {before_status} → {after_status} (changed={result.get('status_changed', False)})", flush=True)
            
            if result.get('status_changed', False):
                old_status = result.get('previous_status', 'UNKNOWN')
                new_status = result['current_status']
                
                print(f"[ALERT_CALL] Calling alert service for {device.name}: {old_status} → {new_status}", flush=True)
                
                self._handle_status_change_alert(
                    device_id=device.device_id,
                    old_status=old_status,
                    new_status=new_status,
                    is_reachable=ping_result['is_reachable']
                )
            
            result['ping_details'] = {
                'min_latency_ms': ping_result['min_latency_ms'],
                'max_latency_ms': ping_result['max_latency_ms'],
                'packet_loss_percent': ping_result['packet_loss_percent'],
                'jitter_ms': ping_result['jitter_ms']
            }
            
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
                
                results = self.check_all_devices()
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
    
    def set_alert_cooldown(self, seconds: int):
        """Set alert cooldown period in seconds (default 600 = 10 minutes)"""
        if seconds >= 0:
            self.alert_cooldown = seconds
            print(f"✅ Alert cooldown set to {seconds} seconds")
        else:
            print(f"⚠️ Invalid cooldown value: {seconds}")
    
    def reset_alert_state(self):
        """Reset alert state for all devices (useful for testing)"""
        self._initial_alert_sent = {}
        self._last_alert_state = {}
        self._last_alert_time = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE devices SET initial_alert_sent = 0")
        except Exception as e:
            print(f"⚠️ Failed to reset database state: {e}")
        self._save_alert_state()
        print("✅ Alert state reset")
    
    def get_devices(self) -> list:
        """Get all devices"""
        return list(self.devices.values())