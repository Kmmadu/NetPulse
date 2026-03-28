#!/usr/bin/env python3
"""
Device Model - Core device state management
NetPulse Network Monitoring System
Now with quality metrics and degraded state detection
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, List
from enum import Enum
import json
import statistics


class DeviceStatus(Enum):
    """Device status enumeration"""
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DEGRADED = "DEGRADED"  # New state for suboptimal performance
    DOWN = "DOWN"
    
    @classmethod
    def from_bool(cls, is_up: Optional[bool]) -> "DeviceStatus":
        """Convert boolean to DeviceStatus"""
        if is_up is None:
            return cls.UNKNOWN
        return cls.UP if is_up else cls.DOWN


class QualityThresholds:
    """Quality thresholds for performance evaluation"""
    
    def __init__(self, 
                 max_latency_ms: float = 100.0,      # Above this = degraded
                 critical_latency_ms: float = 500.0, # Above this = considered down
                 max_jitter_ms: float = 50.0,        # Above this = degraded
                 packet_loss_threshold: float = 5.0, # Above this % = degraded
                 sample_window: int = 10):           # Samples for moving average
        """
        Initialize quality thresholds
        
        Args:
            max_latency_ms: Maximum acceptable latency before considering degraded
            critical_latency_ms: Latency threshold that triggers DOWN
            max_jitter_ms: Maximum acceptable jitter (latency variation)
            packet_loss_threshold: Maximum acceptable packet loss percentage
            sample_window: Number of recent samples for quality calculation
        """
        self.max_latency_ms = max_latency_ms
        self.critical_latency_ms = critical_latency_ms
        self.max_jitter_ms = max_jitter_ms
        self.packet_loss_threshold = packet_loss_threshold
        self.sample_window = sample_window


class QualityMetrics:
    """Track quality metrics for a device over time"""
    
    def __init__(self, window_size: int = 10):
        """
        Initialize quality metrics tracker
        
        Args:
            window_size: Number of samples to keep for calculations
        """
        self.window_size = window_size
        self.samples: List[Dict] = []  # Store recent check results
        self.packet_loss_samples: List[bool] = []  # True = success, False = failure
        
    def add_sample(self, is_reachable: bool, latency_ms: Optional[float]):
        """
        Add a new check sample
        
        Args:
            is_reachable: Whether ping succeeded
            latency_ms: Latency if reachable, None otherwise
        """
        self.samples.append({
            'timestamp': datetime.now(),
            'is_reachable': is_reachable,
            'latency_ms': latency_ms
        })
        
        # Keep only recent samples
        if len(self.samples) > self.window_size:
            self.samples.pop(0)
        
        # Track packet loss
        self.packet_loss_samples.append(is_reachable)
        if len(self.packet_loss_samples) > self.window_size:
            self.packet_loss_samples.pop(0)
    
    @property
    def avg_latency(self) -> Optional[float]:
        """Average latency of successful pings"""
        latencies = [s['latency_ms'] for s in self.samples 
                    if s['is_reachable'] and s['latency_ms'] is not None]
        return statistics.mean(latencies) if latencies else None
    
    @property
    def max_latency(self) -> Optional[float]:
        """Maximum latency of successful pings"""
        latencies = [s['latency_ms'] for s in self.samples 
                    if s['is_reachable'] and s['latency_ms'] is not None]
        return max(latencies) if latencies else None
    
    @property
    def min_latency(self) -> Optional[float]:
        """Minimum latency of successful pings"""
        latencies = [s['latency_ms'] for s in self.samples 
                    if s['is_reachable'] and s['latency_ms'] is not None]
        return min(latencies) if latencies else None
    
    @property
    def jitter(self) -> Optional[float]:
        """
        Calculate jitter (standard deviation of latency)
        High jitter indicates unstable connection
        """
        latencies = [s['latency_ms'] for s in self.samples 
                    if s['is_reachable'] and s['latency_ms'] is not None]
        if len(latencies) >= 2:
            return statistics.stdev(latencies)
        return None
    
    @property
    def packet_loss_percentage(self) -> float:
        """Calculate packet loss percentage over sample window"""
        if not self.packet_loss_samples:
            return 0.0
        failures = sum(1 for s in self.packet_loss_samples if not s)
        return (failures / len(self.packet_loss_samples)) * 100.0
    
    @property
    def sample_count(self) -> int:
        """Number of samples in window"""
        return len(self.samples)
    
    def get_quality_score(self, thresholds: QualityThresholds) -> Dict:
        """
        Evaluate quality based on thresholds
        
        Returns:
            Dict with quality assessment and reason
        """
        issues = []
        quality_score = 100.0  # Start at perfect score
        
        # Check packet loss
        packet_loss = self.packet_loss_percentage
        if packet_loss > thresholds.packet_loss_threshold:
            issues.append(f"Packet loss: {packet_loss:.1f}% > {thresholds.packet_loss_threshold}%")
            quality_score -= min(50, packet_loss * 5)  # Up to 50% reduction
        
        # Check latency
        avg_lat = self.avg_latency
        if avg_lat:
            if avg_lat > thresholds.critical_latency_ms:
                issues.append(f"Critical latency: {avg_lat:.0f}ms > {thresholds.critical_latency_ms}ms")
                quality_score = 0
            elif avg_lat > thresholds.max_latency_ms:
                excess = avg_lat - thresholds.max_latency_ms
                penalty = min(40, excess / thresholds.max_latency_ms * 40)
                issues.append(f"High latency: {avg_lat:.0f}ms > {thresholds.max_latency_ms}ms")
                quality_score -= penalty
        
        # Check jitter
        jitter_val = self.jitter
        if jitter_val and jitter_val > thresholds.max_jitter_ms:
            issues.append(f"High jitter: {jitter_val:.1f}ms > {thresholds.max_jitter_ms}ms")
            quality_score -= min(30, jitter_val / thresholds.max_jitter_ms * 30)
        
        # Determine status
        if quality_score >= 80:
            status = DeviceStatus.UP
            quality_level = "Good"
        elif quality_score >= 50:
            status = DeviceStatus.DEGRADED
            quality_level = "Degraded"
        else:
            status = DeviceStatus.DOWN
            quality_level = "Poor"
        
        return {
            'status': status,
            'quality_score': round(quality_score, 1),
            'quality_level': quality_level,
            'issues': issues,
            'metrics': {
                'avg_latency_ms': round(avg_lat, 1) if avg_lat else None,
                'jitter_ms': round(jitter_val, 1) if jitter_val else None,
                'packet_loss_percent': round(packet_loss, 1),
                'sample_count': self.sample_count
            }
        }


class Device:
    """
    Represents a network device with monitoring state and quality metrics.
    Now supports DEGRADED state for suboptimal performance.
    """
    
    def __init__(self, device_id: str, name: str, ip_address: str, 
                 retry_count: int = 2, timeout: int = 2,
                 quality_thresholds: Optional[QualityThresholds] = None):
        """
        Initialize a device monitor
        
        Args:
            device_id: Unique identifier
            name: Display name
            ip_address: IP address to monitor
            retry_count: Number of consecutive failures before marking DOWN
            timeout: Ping timeout in seconds
            quality_thresholds: Quality thresholds for degraded detection
        """
        # Configuration
        self.device_id = device_id
        self.name = name
        self.ip_address = ip_address
        self.retry_count = max(1, retry_count)
        self.timeout = max(1, timeout)
        self.quality_thresholds = quality_thresholds or QualityThresholds()
        
        # State tracking
        self._current_status = DeviceStatus.UNKNOWN
        self._previous_status = DeviceStatus.UNKNOWN
        self._fail_count = 0
        self._last_check_time = None
        self._last_latency = None
        self._last_state_change = None
        self._last_quality_score = None
        
        # Quality metrics tracking
        self.quality_metrics = QualityMetrics(window_size=10)
        
    @property
    def status(self) -> DeviceStatus:
        """Current device status"""
        return self._current_status
    
    @property
    def status_text(self) -> str:
        """Human-readable status"""
        return self._current_status.value
    
    @property
    def previous_status(self) -> DeviceStatus:
        """Previous status"""
        return self._previous_status
    
    @property
    def fail_count(self) -> int:
        """Current consecutive failure count"""
        return self._fail_count
    
    @property
    def last_latency(self) -> Optional[float]:
        """Last measured latency in ms"""
        return self._last_latency
    
    @property
    def last_check_time(self) -> Optional[datetime]:
        """Timestamp of last check"""
        return self._last_check_time
    
    @property
    def last_state_change(self) -> Optional[datetime]:
        """Timestamp of last status change"""
        return self._last_state_change
    
    @property
    def quality_score(self) -> Optional[float]:
        """Current quality score (0-100)"""
        return self._last_quality_score
    
    def _evaluate_quality(self) -> Dict:
        """
        Evaluate current quality metrics and determine status
        """
        if self.quality_metrics.sample_count < 3:
            # Not enough data yet
            return {
                'status': DeviceStatus.UNKNOWN,
                'quality_score': None,
                'issues': ['Collecting data...']
            }
        
        # If we're in DOWN state from connectivity issues, stay DOWN
        if self._current_status == DeviceStatus.DOWN and self._fail_count >= self.retry_count:
            return {
                'status': DeviceStatus.DOWN,
                'quality_score': 0,
                'issues': ['Device unreachable']
            }
        
        # Evaluate quality based on metrics
        quality = self.quality_metrics.get_quality_score(self.quality_thresholds)
        self._last_quality_score = quality['quality_score']
        
        return quality
    
    def process_check_result(self, is_reachable: bool, latency: Optional[float] = None) -> Dict:
        """
        Process a single check result with quality evaluation
        
        Args:
            is_reachable: True if ping succeeded, False otherwise
            latency: Response time in ms (if reachable)
            
        Returns:
            Dict with complete check result including quality metrics
        """
        # Record check metadata
        self._last_check_time = datetime.now()
        self._last_latency = latency if is_reachable else None
        
        # Add to quality metrics
        self.quality_metrics.add_sample(is_reachable, latency)
        
        # Track state before update
        old_status = self._current_status
        status_changed = False
        new_status = None
        
        # Update connectivity failure counter
        if is_reachable:
            self._fail_count = 0
        else:
            self._fail_count += 1
        
        # Determine base connectivity status
        if not is_reachable and self._fail_count >= self.retry_count:
            # Hard down - unreachable
            new_status = DeviceStatus.DOWN
        elif is_reachable:
            # Reachable - need to evaluate quality
            quality_eval = self._evaluate_quality()
            new_status = quality_eval['status']
        else:
            # Not enough failures yet, maintain current status
            new_status = self._current_status
        
        # Handle status transitions
        if new_status != self._current_status:
            status_changed = True
            self._previous_status = self._current_status
            self._current_status = new_status
            self._last_state_change = self._last_check_time
        
        # Get quality evaluation if reachable
        quality_eval = None
        if is_reachable and self.quality_metrics.sample_count >= 3:
            quality_eval = self._evaluate_quality()
        
        # Prepare structured result
        result = {
            'device_id': self.device_id,
            'name': self.name,
            'ip': self.ip_address,
            'timestamp': self._last_check_time,
            'is_reachable': is_reachable,
            'latency_ms': latency if is_reachable else None,
            'fail_count': self._fail_count,
            'retry_count': self.retry_count,
            'current_status': self._current_status.value,
            'previous_status': old_status.value if old_status else None,
            'status_changed': status_changed,
            'transition_type': self._get_transition_type(old_status, new_status) if status_changed else None,
            'quality': quality_eval
        }
        
        return result
    
    def _get_transition_type(self, old: 'DeviceStatus', new: 'DeviceStatus') -> Optional[str]:
        """Determine the type of state transition"""
        if old == DeviceStatus.UNKNOWN and new == DeviceStatus.UP:
            return "initial_up"
        elif old == DeviceStatus.UNKNOWN and new == DeviceStatus.DEGRADED:
            return "initial_degraded"
        elif old == DeviceStatus.UNKNOWN and new == DeviceStatus.DOWN:
            return "initial_down"
        elif old == DeviceStatus.UP and new == DeviceStatus.DEGRADED:
            return "up_to_degraded"
        elif old == DeviceStatus.UP and new == DeviceStatus.DOWN:
            return "up_to_down"
        elif old == DeviceStatus.DEGRADED and new == DeviceStatus.UP:
            return "degraded_to_up"
        elif old == DeviceStatus.DEGRADED and new == DeviceStatus.DOWN:
            return "degraded_to_down"
        elif old == DeviceStatus.DOWN and new == DeviceStatus.DEGRADED:
            return "down_to_degraded"
        elif old == DeviceStatus.DOWN and new == DeviceStatus.UP:
            return "down_to_up"
        return None
    
    def reset(self):
        """Reset device state"""
        self._current_status = DeviceStatus.UNKNOWN
        self._previous_status = DeviceStatus.UNKNOWN
        self._fail_count = 0
        self._last_check_time = None
        self._last_latency = None
        self._last_state_change = None
        self._last_quality_score = None
        self.quality_metrics = QualityMetrics(window_size=10)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'id': self.device_id,
            'name': self.name,
            'ip_address': self.ip_address,
            'retry_count': self.retry_count,
            'timeout': self.timeout,
            'max_latency_ms': self.quality_thresholds.max_latency_ms,
            'critical_latency_ms': self.quality_thresholds.critical_latency_ms,
            'max_jitter_ms': self.quality_thresholds.max_jitter_ms,
            'packet_loss_threshold': self.quality_thresholds.packet_loss_threshold
        }
    
    def __repr__(self) -> str:
        return f"Device(id={self.device_id}, name={self.name}, status={self.status.value}, fails={self._fail_count}/{self.retry_count})"


# Test the enhanced device model
if __name__ == "__main__":
    print("Testing Enhanced Device Model with Quality Metrics")
    print("="*60)
    
    # Create device with custom thresholds
    thresholds = QualityThresholds(
        max_latency_ms=50.0,      # Above 50ms = degraded
        critical_latency_ms=200.0, # Above 200ms = down
        max_jitter_ms=20.0,        # Above 20ms jitter = degraded
        packet_loss_threshold=5.0  # Above 5% loss = degraded
    )
    
    device = Device("test1", "Test Device", "10.0.0.1", 
                    retry_count=2, quality_thresholds=thresholds)
    
    # Simulate different scenarios
    scenarios = [
        # Scenario 1: Good connection
        [(True, 15.0), (True, 18.0), (True, 20.0), (True, 17.0), (True, 19.0)],
        
        # Scenario 2: High latency (degraded)
        [(True, 80.0), (True, 85.0), (True, 90.0), (True, 82.0), (True, 88.0)],
        
        # Scenario 3: Packet loss (degraded)
        [(False, None), (True, 20.0), (False, None), (True, 22.0), (True, 21.0)],
        
        # Scenario 4: High jitter (degraded)
        [(True, 10.0), (True, 100.0), (True, 15.0), (True, 90.0), (True, 20.0)],
        
        # Scenario 5: Critical latency (down)
        [(True, 250.0), (True, 260.0), (True, 270.0)],
        
        # Scenario 6: Hard down
        [(False, None), (False, None), (False, None)],
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n📊 Scenario {i}:")
        print("-" * 40)
        
        for j, (reachable, latency) in enumerate(scenario, 1):
            result = device.process_check_result(reachable, latency)
            
            # Print check result
            status_icon = "✅" if reachable else "❌"
            latency_str = f"{latency:.1f}ms" if latency else "N/A"
            print(f"  Check {j}: {status_icon} {latency_str} -> {result['current_status']}", end="")
            
            if result.get('quality') and result['quality'].get('issues'):
                issues = result['quality']['issues']
                if issues:
                    print(f" ({', '.join(issues[:2])})")
                else:
                    print()
            else:
                print()
            
            # Show status change
            if result['status_changed']:
                print(f"    ⚡ Status change: {result['previous_status']} → {result['current_status']}")
        
        print(f"\n  Final status: {device.status.value}")
        if device.quality_metrics.sample_count >= 3:
            quality = device.quality_metrics.get_quality_score(thresholds)
            print(f"  Quality score: {quality['quality_score']:.1f}/100 ({quality['quality_level']})")
            if quality['issues']:
                print(f"  Issues: {', '.join(quality['issues'])}")
    
    print("\n" + "="*60)
    print("Test complete!")
