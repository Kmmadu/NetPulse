#!/usr/bin/env python3
"""
Device Model - Simple state machine
"""

from datetime import datetime
from typing import Dict, Optional
from enum import Enum


class DeviceStatus(Enum):
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DOWN = "DOWN"


class Device:
    """Simple device with state machine"""
    
    def __init__(self, device_id: str, name: str, ip_address: str, 
                 retry_count: int = 2, timeout: int = 2):
        self.device_id = device_id
        self.name = name
        self.ip_address = ip_address
        self.retry_count = max(1, retry_count)
        self.timeout = timeout
        
        # State
        self._status = DeviceStatus.UNKNOWN
        self._fail_count = 0
        self._last_check = None
        self._last_latency = None
        self._down_since = None
    
    @property
    def status(self) -> DeviceStatus:
        return self._status
    
    @property
    def status_text(self) -> str:
        return self._status.value
    
    @property
    def fail_count(self) -> int:
        return self._fail_count
    
    @property
    def last_latency(self) -> Optional[float]:
        return self._last_latency
    
    @property
    def downtime_seconds(self) -> Optional[float]:
        if self._status == DeviceStatus.DOWN and self._down_since:
            return (datetime.now() - self._down_since).total_seconds()
        return None
    
    def process_check(self, is_reachable: bool, latency: Optional[float]) -> Dict:
        """Process a ping result"""
        old_status = self._status
        self._last_check = datetime.now()
        self._last_latency = latency if is_reachable else None
        
        # Update failure counter
        if is_reachable:
            self._fail_count = 0
        else:
            self._fail_count += 1
        
        # Determine new status
        if not is_reachable and self._fail_count >= self.retry_count:
            new_status = DeviceStatus.DOWN
        elif is_reachable:
            new_status = DeviceStatus.UP
        else:
            new_status = self._status
        
        # Handle transition
        changed = False
        if new_status != self._status:
            changed = True
            self._status = new_status
            if new_status == DeviceStatus.DOWN:
                self._down_since = self._last_check
            else:
                self._down_since = None
        
        return {
            'device_id': self.device_id,
            'name': self.name,
            'ip': self.ip_address,
            'timestamp': self._last_check,
            'is_reachable': is_reachable,
            'latency_ms': latency,
            'fail_count': self._fail_count,
            'retry_count': self.retry_count,
            'current_status': self._status.value,
            'status_changed': changed,
            'transition_type': self._get_transition(old_status, new_status) if changed else None,
            'downtime_seconds': self.downtime_seconds
        }
    
    def _get_transition(self, old: DeviceStatus, new: DeviceStatus) -> str:
        if old == DeviceStatus.UNKNOWN and new == DeviceStatus.UP:
            return "initial_up"
        if old == DeviceStatus.UNKNOWN and new == DeviceStatus.DOWN:
            return "initial_down"
        if old == DeviceStatus.UP and new == DeviceStatus.DOWN:
            return "up_to_down"
        if old == DeviceStatus.DOWN and new == DeviceStatus.UP:
            return "down_to_up"
        return "unknown"
    
    def to_dict(self) -> Dict:
        return {
            'device_id': self.device_id,
            'name': self.name,
            'ip_address': self.ip_address,
            'retry_count': self.retry_count,
            'timeout': self.timeout
        }
