#!/usr/bin/env python3
"""
Device Model - Advanced with Quality Analyzer Integration
"""

from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum
import statistics

from app.services.quality_analyzer import (
    LinkQualityAnalyzer,
    QualityMetrics,
    QualityThresholds
)
from app.services.suboptimal_detector import detect_suboptimal_link


class DeviceStatus(Enum):
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class Device:
    """Device with advanced quality analysis and degradation detection"""
    
    def __init__(self, device_id: str, name: str, ip_address: str, 
                 retry_count: int = 2, timeout: int = 2,
                 max_latency_ms: float = 200.0,
                 packet_loss_threshold: float = 10.0,
                 sample_window: int = 5):
        self.device_id = device_id
        self.name = name
        self.ip_address = ip_address
        self.retry_count = max(1, retry_count)
        self.timeout = timeout
        
        # Legacy thresholds (kept for backward compatibility)
        self.max_latency_ms = max_latency_ms
        self.packet_loss_threshold = packet_loss_threshold
        
        # Quality analyzer
        thresholds = QualityThresholds(
            latency_degraded=max_latency_ms,
            packet_loss_degraded=packet_loss_threshold
        )
        self.quality_analyzer = LinkQualityAnalyzer(thresholds=thresholds)
        
        # State
        self._status = DeviceStatus.UNKNOWN
        self._fail_count = 0
        self._last_check = None
        self._last_latency = None
        self._down_since = None  # When the current DOWN period started
        self._degraded_since = None
        self._last_quality = None
        self._status_history = []  # Track status changes for stability
        self._initial_alert_sent = False  # Track if initial alert was sent
        
        # Rolling window for quality metrics
        self._latency_samples: List[float] = []
        self._success_samples: List[bool] = []
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
        """Calculate continuous downtime duration"""
        if self._status == DeviceStatus.DOWN and self._down_since:
            return (datetime.now() - self._down_since).total_seconds()
        return None
    
    @property
    def degraded_seconds(self) -> Optional[float]:
        if self._status == DeviceStatus.DEGRADED and self._degraded_since:
            return (datetime.now() - self._degraded_since).total_seconds()
        return None
    
    @property
    def quality_score(self) -> Optional[int]:
        """Get current quality score - 0 for DOWN devices"""
        if self._status == DeviceStatus.DOWN:
            return 0
        if self._last_quality and self._last_quality.get('quality_score'):
            return self._last_quality.get('quality_score')
        return None
    
    @property
    def quality_level(self) -> Optional[str]:
        """Get current quality level"""
        if self._status == DeviceStatus.DOWN:
            return "Down"
        if self._last_quality:
            return self._last_quality.get('quality_level')
        return None
    
    @property
    def initial_alert_sent(self) -> bool:
        """Check if initial alert has been sent"""
        return self._initial_alert_sent
    
    @initial_alert_sent.setter
    def initial_alert_sent(self, value: bool):
        """Set initial alert sent status"""
        self._initial_alert_sent = value
    
    def is_suboptimal(self) -> Dict:
        """Check if the link is suboptimal"""
        return detect_suboptimal_link(self)
    
    def get_suboptimal_report(self) -> Dict:
        """Get detailed suboptimal report"""
        if self._status == DeviceStatus.DOWN:
            return {
                'is_suboptimal': False,
                'severity': 'none',
                'reasons': ['Device is DOWN'],
                'quality_impact': 0,
                'trend': 'stable'
            }
        
        if self._status == DeviceStatus.UP:
            # Check if UP but suboptimal
            return self.is_suboptimal()
        
        if self._status == DeviceStatus.DEGRADED:
            # Already degraded, get detailed analysis
            return self.is_suboptimal()
        
        return {
            'is_suboptimal': False,
            'severity': 'none',
            'reasons': [],
            'quality_impact': 100,
            'trend': 'stable'
        }
    
    def _add_sample(self, is_reachable: bool, latency: Optional[float]):
        """Add a sample to rolling window"""
        self._success_samples.append(is_reachable)
        if len(self._success_samples) > self._sample_window:
            self._success_samples.pop(0)
        
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
    
    def _calculate_jitter(self) -> Optional[float]:
        """Calculate jitter from latency samples"""
        if len(self._latency_samples) < 2:
            return None
        return statistics.stdev(self._latency_samples)
    
    def process_check(self, is_reachable: bool, latency: Optional[float], 
                      is_initial_check: bool = False) -> Dict:
        """
        Process a ping result with quality analysis.
        
        Args:
            is_reachable: Whether the device responded to ping
            latency: Response latency in milliseconds
            is_initial_check: If True, bypass stability check for DOWN detection
                             (used for initial state evaluation on startup)
        """
        old_status = self._status
        self._last_check = datetime.now()
        self._last_latency = latency if is_reachable else None
        
        # Add to rolling window
        self._add_sample(is_reachable, latency)
        
        # Calculate packet loss percentage from rolling window
        packet_loss = self._calculate_packet_loss()
        
        # Update failure counter (for DOWN detection)
        if is_reachable:
            self._fail_count = 0
        else:
            self._fail_count += 1
        
        # Prepare metrics for quality analyzer (only if reachable)
        quality = None
        quality_level = None
        
        if is_reachable:
            metrics = QualityMetrics(
                avg_latency_ms=self._calculate_avg_latency(),
                jitter_ms=self._calculate_jitter(),
                packet_loss_percent=packet_loss,
                sample_count=len(self._success_samples),
                success_count=sum(1 for s in self._success_samples if s),
                failure_count=sum(1 for s in self._success_samples if not s),
                consecutive_failures=self._fail_count,
                state_changes=0,
                timestamp=self._last_check
            )
            
            # Analyze quality only for reachable devices
            quality = self.quality_analyzer.analyze(metrics, old_status.value if old_status else None)
            self._last_quality = quality
            
            if quality and quality.get('quality_level'):
                quality_level = quality['quality_level']
        
        # ============================================================
        # STATUS DETERMINATION LOGIC - PRODUCTION STABLE
        # ============================================================
        # DOWN: Device is NOT reachable AND retry threshold met
        #   - A reachable device is NEVER marked as DOWN
        #
        # UP: Reachable AND packet_loss < 10% AND quality_level == "Good"
        #
        # DEGRADED: Reachable but has quality issues
        #   - packet_loss >= 10% OR quality_level != "Good"
        #
        # UNKNOWN/Previous: Not reachable but retry count not yet met
        # ============================================================
        
        # Capture before status for debugging
        before_status = self._status.value if self._status else "UNKNOWN"
        
        # Rule 1: DOWN - Complete connectivity failure only
        if not is_reachable and self._fail_count >= self.retry_count:
            proposed_status = DeviceStatus.DOWN
        
        # Rule 2: UP - Reachable, good quality, low packet loss
        elif is_reachable and packet_loss < 10.0 and quality_level == 'Good':
            proposed_status = DeviceStatus.UP
        
        # Rule 3: DEGRADED - Reachable but has quality issues
        elif is_reachable:
            proposed_status = DeviceStatus.DEGRADED
        
        # Rule 4: Not reachable but retry count not yet met - maintain current status
        else:
            proposed_status = self._status
        
        # Log status proposal for debugging
        if before_status != proposed_status.value:
            print(f"[STATUS] {self.name}: {before_status} → {proposed_status.value} (pending)", flush=True)
        
        # Determine if status actually changed
        status_changed = (proposed_status != self._status)
        
        # Apply stability check to prevent flapping
        should_transition = self.quality_analyzer.should_transition(proposed_status.value)
        
        # Special handling for initial check: if device is DOWN, force transition
        if is_initial_check and proposed_status == DeviceStatus.DOWN:
            should_transition = True
            print(f"[INITIAL] {self.name}: Forcing DOWN transition", flush=True)
        
        # Log stability block
        if status_changed and not should_transition:
            print(f"[STABILITY] {self.name}: Transition to {proposed_status.value} blocked", flush=True)
        
        if status_changed and should_transition:
            old_status_for_tracking = self._status
            self._status = proposed_status
            print(f"[TRANSITION] {self.name}: {old_status_for_tracking.value} → {self._status.value}", flush=True)
            
            # Track start times - ONLY when transitioning INTO a state
            if self._status == DeviceStatus.DOWN and old_status_for_tracking != DeviceStatus.DOWN:
                # Just entered DOWN state - record start time
                self._down_since = self._last_check
                self._degraded_since = None
                print(f"[DOWN] {self.name} entered DOWN state at {self._down_since}", flush=True)
            elif self._status == DeviceStatus.DEGRADED and old_status_for_tracking != DeviceStatus.DEGRADED:
                # Just entered DEGRADED state - record start time
                self._degraded_since = self._last_check
                self._down_since = None
                print(f"[DEGRADED] {self.name} entered DEGRADED state at {self._degraded_since}", flush=True)
            elif self._status in [DeviceStatus.UP, DeviceStatus.UNKNOWN]:
                # Exiting DOWN or DEGRADED - clear timers
                self._down_since = None
                self._degraded_since = None
        else:
            status_changed = False
        
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
            'status_changed': status_changed,
            'previous_status': old_status.value if old_status else "UNKNOWN",
            'transition_type': self._get_transition(old_status, self._status) if status_changed else None,
            'downtime_seconds': self.downtime_seconds,
            'degraded_seconds': self.degraded_seconds,
            'packet_loss_percent': packet_loss,
            'avg_latency_ms': self._calculate_avg_latency(),
            'sample_count': len(self._success_samples),
            'quality': quality,
            'suboptimal': self.get_suboptimal_report(),
            'is_initial_check': is_initial_check
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
    
    def get_down_since(self) -> Optional[datetime]:
        """Return timestamp when device went down, or None if not down"""
        if self._status == DeviceStatus.DOWN:
            return self._down_since
        return None
    
    def get_quality_report(self) -> Dict:
        """Get detailed quality report for this device"""
        if self._status == DeviceStatus.DOWN:
            return {
                'quality_score': 0,
                'quality_level': 'Down',
                'confidence': 1.0,
                'issues': ['Device is DOWN - unreachable'],
                'degradation_type': 'unreachable'
            }
        if self._last_quality:
            return self._last_quality
        return {
            'quality_score': None,
            'quality_level': 'Unknown',
            'confidence': 0,
            'issues': [],
            'degradation_type': 'none'
        }
    
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