#!/usr/bin/env python3
"""
Device Model - Simple with DEGRADED detection
"""

from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum
import statistics


class DeviceStatus(Enum):
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DEGRADED = "DEGRADED"  # Suboptimal but reachable
    DOWN = "DOWN"


class Device:
    """Device with simple degraded detection"""
    
    def __init__(self, device_id: str, name: str, ip_address: str, 
                 retry_count: int = 2, timeout: int = 2,
                 max_latency_ms: float = 200.0,    # Above this = degraded
                 packet_loss_threshold: float = 10.0,  # Above this % = degraded
                 sample_window: int = 5):         # How many samples to track
        self.device_id = device_id
        self.name = name
        self.ip_address = ip_address
        self.retry_count = max(1, retry_count)
        self.timeout = timeout
        
        # Degraded thresholds
        self.max_latency_ms = max_latency_ms
        self.packet_loss_threshold = packet_loss_threshold
        
        # State
        self._status = DeviceStatus.UNKNOWN
        self._fail_count = 0
        self._last_check = None
        self._last_latency = None
        self._down_since = None
        self._degraded_since = None  # Track when degraded started
        
        # Rolling window for quality metrics
        self._latency_samples: List[float] = []
        self._success_samples: List[bool] = []  # True = success, False = failure
        self._sample_window = sample_window
    
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
    
    @property
    def degraded_seconds(self) -> Optional[float]:
        if self._status == DeviceStatus.DEGRADED and self._degraded_since:
            return (datetime.now() - self._degraded_since).total_seconds()
        return None
    
    def _add_sample(self, is_reachable: bool, latency: Optional[float]):
        """Add a sample to rolling window"""
        # Track success/failure
        self._success_samples.append(is_reachable)
        if len(self._success_samples) > self._sample_window:
            self._success_samples.pop(0)
        
        # Track latency (only for successful pings)
        if is_reachable and latency:
            self._latency_samples.append(latency)
            if len(self._latency_samples) > self._sample_window:
                self._latency_samples.pop(0)
    
    def _calculate_packet_loss(self) -> float:
        """Calculate packet loss percentage over sample window"""
        if not self._success_samples:
            return 0.0
        failures = sum(1 for s in self._success_samples if not s)
        return (failures / len(self._success_samples)) * 100.0
    
    def _calculate_avg_latency(self) -> Optional[float]:
        """Calculate average latency over sample window"""
        if not self._latency_samples:
            return None
        return sum(self._latency_samples) / len(self._latency_samples)
    
    def _is_degraded(self) -> bool:
        """
        Determine if current performance is degraded.
        Returns True if:
        - Packet loss > threshold, OR
        - Average latency > threshold
        """
        # Need enough samples for reliable detection
        if len(self._success_samples) < 3:
            return False
        
        packet_loss = self._calculate_packet_loss()
        if packet_loss > self.packet_loss_threshold:
            return True
        
        avg_latency = self._calculate_avg_latency()
        if avg_latency and avg_latency > self.max_latency_ms:
            return True
        
        return False
    
    def process_check(self, is_reachable: bool, latency: Optional[float]) -> Dict:
        """Process a ping result with degraded detection"""
        old_status = self._status
        self._last_check = datetime.now()
        self._last_latency = latency if is_reachable else None
        
        # Add to rolling window
        self._add_sample(is_reachable, latency)
        
        # Update failure counter (for DOWN detection)
        if is_reachable:
            self._fail_count = 0
        else:
            self._fail_count += 1
        
        # Determine new status
        # 1. Check if DOWN (unreachable)
        if not is_reachable and self._fail_count >= self.retry_count:
            new_status = DeviceStatus.DOWN
        
        # 2. Check if DEGRADED (reachable but poor performance)
        elif is_reachable and self._is_degraded():
            new_status = DeviceStatus.DEGRADED
        
        # 3. Normal UP
        elif is_reachable:
            new_status = DeviceStatus.UP
        
        # 4. Not enough failures yet, maintain current status
        else:
            new_status = self._status
        
        # Handle transition
        changed = False
        if new_status != self._status:
            changed = True
            self._status = new_status
            
            # Track start times for DOWN and DEGRADED
            if new_status == DeviceStatus.DOWN:
                self._down_since = self._last_check
                self._degraded_since = None
            elif new_status == DeviceStatus.DEGRADED:
                self._degraded_since = self._last_check
                self._down_since = None
            else:
                self._down_since = None
                self._degraded_since = None
        
        # Prepare result with quality metrics
        result = {
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
            'downtime_seconds': self.downtime_seconds,
            'degraded_seconds': self.degraded_seconds,
            # Quality metrics
            'packet_loss_percent': self._calculate_packet_loss(),
            'avg_latency_ms': self._calculate_avg_latency(),
            'sample_count': len(self._success_samples)
        }
        
        return result
    
    def _get_transition(self, old: DeviceStatus, new: DeviceStatus) -> str:
        transitions = {
            (DeviceStatus.UNKNOWN, DeviceStatus.UP): "initial_up",
            (DeviceStatus.UNKNOWN, DeviceStatus.DEGRADED): "initial_degraded",
            (DeviceStatus.UNKNOWN, DeviceStatus.DOWN): "initial_down",
            (DeviceStatus.UP, DeviceStatus.DEGRADED): "up_to_degraded",
            (DeviceStatus.UP, DeviceStatus.DOWN): "up_to_down",
            (DeviceStatus.DEGRADED, DeviceStatus.UP): "degraded_to_up",
            (DeviceStatus.DEGRADED, DeviceStatus.DOWN): "degraded_to_down",
            (DeviceStatus.DOWN, DeviceStatus.DEGRADED): "down_to_degraded",
            (DeviceStatus.DOWN, DeviceStatus.UP): "down_to_up",
        }
        return transitions.get((old, new), "unknown")
    
    def to_dict(self) -> Dict:
        return {
            'device_id': self.device_id,
            'name': self.name,
            'ip_address': self.ip_address,
            'retry_count': self.retry_count,
            'timeout': self.timeout,
            'max_latency_ms': self.max_latency_ms,
            'packet_loss_threshold': self.packet_loss_threshold
        }
