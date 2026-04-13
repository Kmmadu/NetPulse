#!/usr/bin/env python3
"""
Advanced Suboptimal Link Detection System
Detects when a link is performing poorly but not completely down
Stateful detection with success rate, packet loss override, and trend analysis
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
import statistics
from enum import Enum


class SuboptimalSeverity(Enum):
    """Severity levels for suboptimal links"""
    NONE = "none"          # Normal operation
    MILD = "mild"          # Slightly degraded (e.g., 50-100ms latency)
    MODERATE = "moderate"  # Noticeable degradation (e.g., 5-15% loss)
    SEVERE = "severe"      # Severely degraded (e.g., >15% loss, <50% success)
    CRITICAL = "critical"  # Near-down condition (e.g., >30% loss, <30% success)


@dataclass
class SuboptimalMetrics:
    """Metrics for suboptimal detection - stateful across calls"""
    # Core metrics
    avg_latency_ms: Optional[float] = None
    packet_loss_percent: float = 0.0
    jitter_ms: Optional[float] = None
    success_rate: float = 100.0  # New: percentage of successful pings
    
    # Sample tracking
    sample_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    
    # Poor sample tracking (any metric above threshold)
    consecutive_poor_samples: int = 0
    total_poor_samples: int = 0
    sample_window: int = 10
    
    # Stability tracking
    flapping_count: int = 0
    state_changes: int = 0


class SuboptimalDetector:
    """
    Stateful advanced suboptimal link detection with trend analysis.
    Detects when a link is working but performing poorly.
    
    Features:
    - Success rate detection (critical for real-world monitoring)
    - Packet loss override (severe loss = severe degradation)
    - Stateful history preservation
    - Proper consecutive poor sample tracking
    - Trend analysis with rapid degradation detection
    """
    
    def __init__(self, 
                 latency_threshold_ms: float = 100.0,
                 packet_loss_threshold: float = 5.0,
                 jitter_threshold_ms: float = 30.0,
                 required_consecutive_samples: int = 3,
                 poor_sample_threshold: float = 0.6):  # 60% of criteria met = poor sample
        """
        Initialize the suboptimal detector.
        
        Args:
            latency_threshold_ms: Latency above this is considered degraded
            packet_loss_threshold: Packet loss above this is considered degraded
            jitter_threshold_ms: Jitter above this is considered degraded
            required_consecutive_samples: Required consecutive poor samples for confirmation
            poor_sample_threshold: Percentage of criteria that must be met for "poor sample"
        """
        self.latency_threshold_ms = latency_threshold_ms
        self.packet_loss_threshold = packet_loss_threshold
        self.jitter_threshold_ms = jitter_threshold_ms
        self.required_consecutive_samples = required_consecutive_samples
        self.poor_sample_threshold = poor_sample_threshold
        
        # Rolling windows for trend analysis (stateful)
        self.latency_history = deque(maxlen=30)
        self.packet_loss_history = deque(maxlen=30)
        self.jitter_history = deque(maxlen=30)
        self.success_rate_history = deque(maxlen=30)
        self.quality_history = deque(maxlen=30)
        
        # Track consecutive poor samples across calls
        self._consecutive_poor_counter = 0
        self._last_sample_was_poor = False
        
        # Track rapid degradation
        self._previous_quality_scores = deque(maxlen=5)
    
    def _is_poor_sample(self, metrics: SuboptimalMetrics) -> bool:
        """
        Determine if a single sample is "poor" based on multiple criteria.
        A poor sample is when ANY of the following are true:
        - Latency > threshold
        - Packet loss > threshold
        - Jitter > threshold
        - Success rate < 80%
        """
        criteria_met = 0
        total_criteria = 0
        
        # Check latency
        if metrics.avg_latency_ms is not None:
            total_criteria += 1
            if metrics.avg_latency_ms > self.latency_threshold_ms:
                criteria_met += 1
        
        # Check packet loss
        if metrics.packet_loss_percent > 0:
            total_criteria += 1
            if metrics.packet_loss_percent > self.packet_loss_threshold:
                criteria_met += 1
        
        # Check jitter
        if metrics.jitter_ms is not None:
            total_criteria += 1
            if metrics.jitter_ms > self.jitter_threshold_ms:
                criteria_met += 1
        
        # Check success rate
        total_criteria += 1
        if metrics.success_rate < 80.0:
            criteria_met += 1
        
        if total_criteria == 0:
            return False
        
        # Sample is poor if any single criterion is met, or if multiple are borderline
        return criteria_met > 0
    
    def _update_consecutive_poor_samples(self, metrics: SuboptimalMetrics, is_poor: bool) -> int:
        """Update and return consecutive poor samples count"""
        if is_poor:
            self._consecutive_poor_counter += 1
        else:
            self._consecutive_poor_counter = 0
        
        # Update metrics with the current counter
        metrics.consecutive_poor_samples = self._consecutive_poor_counter
        return self._consecutive_poor_counter
    
    def _update_histories(self, metrics: SuboptimalMetrics):
        """Update all rolling histories"""
        if metrics.avg_latency_ms:
            self.latency_history.append(metrics.avg_latency_ms)
        if metrics.packet_loss_percent > 0:
            self.packet_loss_history.append(metrics.packet_loss_percent)
        if metrics.jitter_ms:
            self.jitter_history.append(metrics.jitter_ms)
        
        self.success_rate_history.append(metrics.success_rate)
    
    def _calculate_success_rate_score(self, success_rate: float) -> float:
        """
        Calculate severity contribution from success rate.
        Success rate is CRITICAL for real-world monitoring.
        
        Returns severity score (0-100, higher = worse)
        """
        if success_rate >= 95:
            return 0
        elif success_rate >= 80:
            return 10  # Mild degradation
        elif success_rate >= 60:
            return 30  # Moderate degradation
        elif success_rate >= 40:
            return 60  # Severe degradation
        elif success_rate >= 20:
            return 80  # Critical - near down
        else:
            return 100  # Effectively down
    
    def _calculate_packet_loss_score(self, packet_loss: float) -> float:
        """Calculate severity score from packet loss"""
        if packet_loss >= 50:
            return 100  # Severe - immediate override
        elif packet_loss >= 30:
            return 80
        elif packet_loss >= 15:
            return 60
        elif packet_loss >= 10:
            return 40
        elif packet_loss >= self.packet_loss_threshold:
            return 20
        return 0
    
    def _calculate_latency_score(self, latency: Optional[float]) -> float:
        """Calculate severity score from latency"""
        if latency is None:
            return 0
        
        if latency >= 1000:
            return 100
        elif latency >= 500:
            return 80
        elif latency >= 200:
            return 50
        elif latency >= self.latency_threshold_ms:
            return 25
        return 0
    
    def _calculate_jitter_score(self, jitter: Optional[float]) -> float:
        """Calculate severity score from jitter"""
        if jitter is None:
            return 0
        
        if jitter >= 200:
            return 80
        elif jitter >= 100:
            return 50
        elif jitter >= self.jitter_threshold_ms:
            return 25
        return 0
    
    def _calculate_stability_score(self, metrics: SuboptimalMetrics) -> float:
        """Calculate severity score from stability metrics"""
        score = 0
        
        # Consecutive poor samples
        if metrics.consecutive_poor_samples >= self.required_consecutive_samples:
            score += min(40, metrics.consecutive_poor_samples * 8)
        
        # Flapping detection
        if metrics.flapping_count > 3:
            score += min(30, metrics.flapping_count * 5)
        
        # State changes
        if metrics.state_changes > 3:
            score += min(20, metrics.state_changes * 3)
        
        return min(100, score)
    
    def _detect_rapid_degradation(self, current_score: float) -> bool:
        """
        Detect rapid degradation by comparing last 3 quality scores.
        Returns True if quality dropped significantly in short period.
        """
        if len(self._previous_quality_scores) < 3:
            self._previous_quality_scores.append(current_score)
            return False
        
        self._previous_quality_scores.append(current_score)
        
        if len(self._previous_quality_scores) >= 3:
            recent = list(self._previous_quality_scores)[-3:]
            drop = recent[0] - recent[-1]  # Positive = degradation
            if drop > 25:  # Dropped more than 25 points in last 3 samples
                return True
        
        return False
    
    def _calculate_trend(self) -> str:
        """
        Calculate trend direction from history with rapid degradation detection.
        """
        if len(self.latency_history) < 5:
            return 'stable'
        
        # Check for rapid degradation in quality scores
        if len(self._previous_quality_scores) >= 3:
            recent = list(self._previous_quality_scores)[-3:]
            drop = recent[0] - recent[-1]
            if drop > 25:
                return 'rapid_degrading'
        
        # Standard slope calculation for latency trend
        recent = list(self.latency_history)[-5:]
        if len(recent) >= 5:
            x = list(range(len(recent)))
            y = recent
            n = len(x)
            mean_x = sum(x) / n
            mean_y = sum(y) / n
            numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
            denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
            
            if denominator > 0:
                slope = numerator / denominator
                if slope > 10:
                    return 'rapid_degrading'
                elif slope > 3:
                    return 'degrading'
                elif slope < -3:
                    return 'improving'
        
        return 'stable'
    
    def analyze(self, metrics: SuboptimalMetrics) -> Dict:
        """
        Analyze if link is suboptimal and return detailed assessment.
        
        Args:
            metrics: SuboptimalMetrics containing current sample data
        
        Returns:
            Dict with comprehensive quality assessment
        """
        reasons = []
        severity_score = 0.0
        is_suboptimal = False
        
        # Update histories first
        self._update_histories(metrics)
        
        # Determine if this is a poor sample and update counter
        is_poor = self._is_poor_sample(metrics)
        self._update_consecutive_poor_samples(metrics, is_poor)
        
        # Calculate component scores
        success_rate_score = self._calculate_success_rate_score(metrics.success_rate)
        packet_loss_score = self._calculate_packet_loss_score(metrics.packet_loss_percent)
        latency_score = self._calculate_latency_score(metrics.avg_latency_ms)
        jitter_score = self._calculate_jitter_score(metrics.jitter_ms)
        stability_score = self._calculate_stability_score(metrics)
        
        # PACKET LOSS OVERRIDE (CRITICAL)
        # High packet loss overrides other metrics
        if metrics.packet_loss_percent >= 50:
            severity_score = 100
            is_suboptimal = True
            reasons.append(f"CRITICAL: Extreme packet loss ({metrics.packet_loss_percent:.1f}%)")
        elif metrics.packet_loss_percent >= 30:
            severity_score = max(severity_score, 80)
            is_suboptimal = True
            reasons.append(f"Severe packet loss: {metrics.packet_loss_percent:.1f}%")
        
        # SUCCESS RATE OVERRIDE (CRITICAL FOR REAL-WORLD)
        # Low success rate indicates near-down condition
        if metrics.success_rate < 30:
            severity_score = max(severity_score, 90)
            is_suboptimal = True
            reasons.append(f"CRITICAL: Very low success rate ({metrics.success_rate:.0f}%)")
        elif metrics.success_rate < 50:
            severity_score = max(severity_score, 70)
            is_suboptimal = True
            reasons.append(f"Low success rate: {metrics.success_rate:.0f}%")
        elif metrics.success_rate < 80:
            severity_score = max(severity_score, 40)
            is_suboptimal = True
            reasons.append(f"Moderate success rate: {metrics.success_rate:.0f}%")
        
        # Add other degradation reasons
        if packet_loss_score > 0 and metrics.packet_loss_percent < 30:
            is_suboptimal = True
            severity_score = max(severity_score, packet_loss_score)
            if "packet loss" not in str(reasons).lower():
                reasons.append(f"Packet loss: {metrics.packet_loss_percent:.1f}%")
        
        if latency_score > 0:
            is_suboptimal = True
            severity_score = max(severity_score, latency_score)
            if "latency" not in str(reasons).lower():
                reasons.append(f"High latency: {metrics.avg_latency_ms:.0f}ms")
        
        if jitter_score > 0:
            is_suboptimal = True
            severity_score = max(severity_score, jitter_score)
            if "jitter" not in str(reasons).lower():
                reasons.append(f"High jitter: {metrics.jitter_ms:.1f}ms")
        
        if stability_score > 0:
            is_suboptimal = True
            severity_score = max(severity_score, stability_score)
            if "unstable" not in str(reasons).lower() and metrics.consecutive_poor_samples >= self.required_consecutive_samples:
                reasons.append(f"Consistent poor performance ({metrics.consecutive_poor_samples} checks)")
        
        # Clamp severity score
        severity_score = min(100, max(0, severity_score))
        
        # Determine severity level
        if severity_score >= 80:
            severity = SuboptimalSeverity.SEVERE
        elif severity_score >= 60:
            severity = SuboptimalSeverity.MODERATE
        elif severity_score >= 30:
            severity = SuboptimalSeverity.MILD
        elif severity_score > 0:
            severity = SuboptimalSeverity.MILD
        else:
            severity = SuboptimalSeverity.NONE
        
        # Calculate quality impact (0-100, lower = worse)
        quality_impact = 100 - severity_score
        
        # Calculate trend with rapid degradation detection
        trend = self._calculate_trend()
        
        # Detect rapid degradation
        current_quality = quality_impact
        rapid_degradation = self._detect_rapid_degradation(current_quality)
        
        if rapid_degradation and "rapid degradation" not in str(reasons):
            reasons.append("Rapid degradation detected")
            if severity == SuboptimalSeverity.MILD:
                severity = SuboptimalSeverity.MODERATE
        
        # Prepare result
        result = {
            'is_suboptimal': is_suboptimal,
            'severity': severity.value,
            'reasons': reasons,
            'quality_impact': round(quality_impact),
            'trend': trend,
            'severity_score': round(severity_score, 1),
            'success_rate': round(metrics.success_rate, 1),
            'component_scores': {
                'success_rate': round(success_rate_score),
                'packet_loss': round(packet_loss_score),
                'latency': round(latency_score),
                'jitter': round(jitter_score),
                'stability': round(stability_score)
            },
            'metrics_summary': {
                'avg_latency_ms': metrics.avg_latency_ms,
                'packet_loss_percent': round(metrics.packet_loss_percent, 1),
                'jitter_ms': metrics.jitter_ms,
                'success_rate': round(metrics.success_rate, 1),
                'consecutive_poor_samples': metrics.consecutive_poor_samples,
                'sample_count': metrics.sample_count
            }
        }
        
        # Add critical indicator if applicable
        if severity_score >= 80:
            result['critical'] = True
            result['near_down'] = (metrics.success_rate < 50 or metrics.packet_loss_percent > 30)
        
        return result
    
    def reset(self):
        """Reset detector state (useful for device removal or reset)"""
        self.latency_history.clear()
        self.packet_loss_history.clear()
        self.jitter_history.clear()
        self.success_rate_history.clear()
        self.quality_history.clear()
        self._consecutive_poor_counter = 0
        self._last_sample_was_poor = False
        self._previous_quality_scores.clear()


# Global detector instances per device (to be managed by Device class)
_detectors = {}


def get_detector_for_device(device_id: str) -> SuboptimalDetector:
    """
    Get or create a stateful detector for a specific device.
    
    Args:
        device_id: Unique device identifier
    
    Returns:
        SuboptimalDetector instance for the device
    """
    if device_id not in _detectors:
        _detectors[device_id] = SuboptimalDetector()
    return _detectors[device_id]


def detect_suboptimal_link(device) -> Dict:
    """
    Convenience function to detect if a device link is suboptimal.
    Uses stateful detector per device.
    
    Args:
        device: Device object with metrics
    
    Returns:
        Dict with suboptimal detection results
    """
    # Get or create stateful detector for this device
    detector = get_detector_for_device(device.device_id)
    
    # Calculate metrics from device
    packet_loss = 0.0
    avg_latency = None
    jitter = None
    consecutive_failures = 0
    sample_count = 0
    success_count = 0
    
    if hasattr(device, '_calculate_packet_loss'):
        packet_loss = device._calculate_packet_loss()
    if hasattr(device, '_calculate_avg_latency'):
        avg_latency = device._calculate_avg_latency()
    if hasattr(device, '_calculate_jitter'):
        jitter = device._calculate_jitter()
    if hasattr(device, 'fail_count'):
        consecutive_failures = device.fail_count
    
    # Calculate sample metrics
    if hasattr(device, '_success_samples'):
        sample_count = len(device._success_samples)
        success_count = sum(1 for s in device._success_samples if s)
    
    # Calculate success rate
    success_rate = 100.0
    if sample_count > 0:
        success_rate = (success_count / sample_count) * 100
    
    # Create metrics object
    metrics = SuboptimalMetrics(
        avg_latency_ms=avg_latency,
        packet_loss_percent=packet_loss,
        jitter_ms=jitter,
        success_rate=success_rate,
        sample_count=sample_count,
        success_count=success_count,
        failure_count=sample_count - success_count,
        consecutive_poor_samples=consecutive_failures,
        flapping_count=getattr(device, '_flapping_count', 0),
        state_changes=getattr(device, '_state_change_count', 0)
    )
    
    return detector.analyze(metrics)