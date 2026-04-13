#!/usr/bin/env python3
"""
Advanced Link Quality Analyzer for NetPulse
Multi-signal suboptimal link detection with confidence scoring and trend analysis
"""

import statistics
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import math


class DegradationType(Enum):
    """Types of link degradation (ordered by severity)"""
    NONE = "none"
    PACKET_LOSS = "packet_loss"
    HIGH_JITTER = "high_jitter"
    HIGH_LATENCY = "high_latency"
    UNSTABLE = "unstable"
    CRITICAL_LATENCY = "critical_latency"
    MULTI_FACTOR = "multi_factor"  # Only when multiple severe issues


class QualityLevel(Enum):
    """Quality levels with thresholds"""
    GOOD = "Good"          # 70-100
    DEGRADED = "Degraded"  # 40-69
    POOR = "Poor"          # 20-39
    CRITICAL = "Critical"  # 0-19


@dataclass
class QualityThresholds:
    """Dynamic thresholds for quality classification"""
    # Packet loss thresholds (%)
    packet_loss_good: float = 0.0
    packet_loss_degraded: float = 2.0
    packet_loss_poor: float = 5.0
    packet_loss_critical: float = 10.0
    
    # Latency thresholds (ms)
    latency_good: float = 50.0
    latency_degraded: float = 100.0
    latency_poor: float = 200.0
    latency_critical: float = 500.0
    
    # Jitter thresholds (ms)
    jitter_good: float = 10.0
    jitter_degraded: float = 25.0
    jitter_poor: float = 50.0
    jitter_critical: float = 100.0
    
    # Stability thresholds
    stability_window: int = 10
    max_state_changes: int = 3
    consecutive_failures_threshold: int = 3
    required_consistent_samples: int = 3
    
    # Sample confidence
    min_confidence_samples: int = 5
    full_confidence_samples: int = 20
    
    # Scoring weights (must sum to 1.0)
    weight_packet_loss: float = 0.35
    weight_latency: float = 0.30
    weight_jitter: float = 0.20
    weight_stability: float = 0.15
    
    def __post_init__(self):
        """Validate that weights sum to 1.0"""
        total = (self.weight_packet_loss + self.weight_latency + 
                 self.weight_jitter + self.weight_stability)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")


@dataclass
class QualityMetrics:
    """Quality metrics for a sample window"""
    avg_latency_ms: Optional[float] = None
    min_latency_ms: Optional[float] = None
    max_latency_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    packet_loss_percent: float = 0.0
    sample_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    state_changes: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def confidence(self) -> float:
        """Calculate confidence based on sample count"""
        if self.sample_count == 0:
            return 0.0
        return min(1.0, self.sample_count / 20)


class StateTracker:
    """Tracks device state changes for flapping detection"""
    
    def __init__(self, window_size: int = 10):
        self.history: deque = deque(maxlen=window_size)
        self._pending_status: Optional[str] = None
        self._stability_counter: int = 0
    
    def add_state(self, status: str) -> int:
        """Add a state to history and return number of changes in window."""
        if self.history and self.history[-1] != status:
            self.history.append(status)
        elif not self.history:
            self.history.append(status)
        return self._count_changes()
    
    def _count_changes(self) -> int:
        """Count number of state transitions in history"""
        if len(self.history) < 2:
            return 0
        changes = 0
        for i in range(1, len(self.history)):
            if self.history[i] != self.history[i-1]:
                changes += 1
        return changes
    
    def should_change_status(self, proposed_status: str, required_cycles: int = 3) -> bool:
        """Determine if status should change based on stability requirements."""
        if proposed_status == self._pending_status:
            self._stability_counter += 1
            if self._stability_counter >= required_cycles:
                self._stability_counter = 0
                self._pending_status = None
                return True
        else:
            self._pending_status = proposed_status
            self._stability_counter = 1
        return False
    
    def is_flapping(self, threshold: int = 5) -> bool:
        """Check if device is flapping (too many state changes)"""
        return self._count_changes() > threshold
    
    def reset(self):
        """Reset state tracker"""
        self.history.clear()
        self._pending_status = None
        self._stability_counter = 0


class TrendAnalyzer:
    """Analyzes quality trends to predict degradation"""
    
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.scores: deque = deque(maxlen=window_size)
        self.timestamps: deque = deque(maxlen=window_size)
        self._early_warning_threshold: float = 5.0
    
    def add_sample(self, score: float, timestamp: datetime):
        """Add a quality score sample."""
        self.scores.append(score)
        self.timestamps.append(timestamp)
    
    def get_trend(self) -> Optional[str]:
        """Analyze trend direction."""
        if len(self.scores) < 5:
            return None
        
        n = len(self.scores)
        x = list(range(n))
        y = list(self.scores)
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
        
        if denominator == 0:
            return None
        
        slope = numerator / denominator
        
        if slope > 1.5:
            return 'improving'
        elif slope < -1.5:
            return 'degrading'
        else:
            return 'stable'
    
    def early_warning(self) -> bool:
        """Check if trend indicates imminent degradation."""
        if len(self.scores) < 3:
            return False
        
        recent = list(self.scores)[-3:]
        if len(recent) >= 3:
            drop = recent[-1] - recent[0]
            if drop < -self._early_warning_threshold:
                return True
        
        trend = self.get_trend()
        return trend == 'degrading'
    
    def predict_next_score(self) -> Optional[float]:
        """Predict next quality score using linear regression."""
        if len(self.scores) < 5:
            return None
        
        n = len(self.scores)
        x = list(range(n))
        y = list(self.scores)
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
        
        if denominator == 0:
            return None
        
        slope = numerator / denominator
        intercept = mean_y - slope * mean_x
        
        predicted = slope * n + intercept
        return max(0, min(100, predicted))
    
    def get_volatility(self) -> Optional[float]:
        """Calculate volatility (standard deviation) of recent scores."""
        if len(self.scores) < 3:
            return None
        return round(statistics.stdev(self.scores), 1)


class LinkQualityAnalyzer:
    """Advanced link quality analyzer with confidence scoring and trend detection."""
    
    def __init__(self, thresholds: Optional[QualityThresholds] = None):
        self.thresholds = thresholds or QualityThresholds()
        self.state_tracker = StateTracker(window_size=self.thresholds.stability_window)
        self.trend_analyzer = TrendAnalyzer()
    
    def _clamp_score(self, score: float) -> float:
        """Ensure score is between 0 and 100."""
        return max(0.0, min(100.0, score))
    
    def _score_packet_loss(self, packet_loss: float) -> float:
        """Score packet loss on a scale of 0-100."""
        if packet_loss <= self.thresholds.packet_loss_good:
            return 100.0
        elif packet_loss >= self.thresholds.packet_loss_critical:
            return 0.0
        elif packet_loss <= self.thresholds.packet_loss_degraded:
            ratio = (packet_loss - self.thresholds.packet_loss_good) / \
                    (self.thresholds.packet_loss_degraded - self.thresholds.packet_loss_good)
            return self._clamp_score(100.0 - (ratio * 25.0))
        elif packet_loss <= self.thresholds.packet_loss_poor:
            ratio = (packet_loss - self.thresholds.packet_loss_degraded) / \
                    (self.thresholds.packet_loss_poor - self.thresholds.packet_loss_degraded)
            return self._clamp_score(75.0 - (ratio * 35.0))
        else:
            ratio = (packet_loss - self.thresholds.packet_loss_poor) / \
                    (self.thresholds.packet_loss_critical - self.thresholds.packet_loss_poor)
            return self._clamp_score(40.0 - (ratio * 40.0))
    
    def _score_latency(self, latency_ms: Optional[float]) -> float:
        """Score latency on a scale of 0-100."""
        if latency_ms is None:
            return 0.0
        
        if latency_ms <= self.thresholds.latency_good:
            return 100.0
        elif latency_ms >= self.thresholds.latency_critical:
            return 0.0
        elif latency_ms <= self.thresholds.latency_degraded:
            ratio = (latency_ms - self.thresholds.latency_good) / \
                    (self.thresholds.latency_degraded - self.thresholds.latency_good)
            return self._clamp_score(100.0 - (ratio * 25.0))
        elif latency_ms <= self.thresholds.latency_poor:
            ratio = (latency_ms - self.thresholds.latency_degraded) / \
                    (self.thresholds.latency_poor - self.thresholds.latency_degraded)
            return self._clamp_score(75.0 - (ratio * 35.0))
        else:
            ratio = (latency_ms - self.thresholds.latency_poor) / \
                    (self.thresholds.latency_critical - self.thresholds.latency_poor)
            return self._clamp_score(40.0 - (ratio * 40.0))
    
    def _score_jitter(self, jitter_ms: Optional[float]) -> float:
        """Score jitter on a scale of 0-100."""
        if jitter_ms is None:
            return 100.0
        
        if jitter_ms <= self.thresholds.jitter_good:
            return 100.0
        elif jitter_ms >= self.thresholds.jitter_critical:
            return 0.0
        elif jitter_ms <= self.thresholds.jitter_degraded:
            ratio = (jitter_ms - self.thresholds.jitter_good) / \
                    (self.thresholds.jitter_degraded - self.thresholds.jitter_good)
            return self._clamp_score(100.0 - (ratio * 25.0))
        elif jitter_ms <= self.thresholds.jitter_poor:
            ratio = (jitter_ms - self.thresholds.jitter_degraded) / \
                    (self.thresholds.jitter_poor - self.thresholds.jitter_degraded)
            return self._clamp_score(75.0 - (ratio * 35.0))
        else:
            ratio = (jitter_ms - self.thresholds.jitter_poor) / \
                    (self.thresholds.jitter_critical - self.thresholds.jitter_poor)
            return self._clamp_score(40.0 - (ratio * 40.0))
    
    def _score_stability(self, metrics: QualityMetrics) -> float:
        """Score stability based on state changes and consecutive failures."""
        score = 100.0
        
        if metrics.state_changes > self.thresholds.max_state_changes:
            penalty = min(50, (metrics.state_changes - self.thresholds.max_state_changes) * 10)
            score -= penalty
        
        if metrics.consecutive_failures >= self.thresholds.consecutive_failures_threshold:
            penalty = min(30, metrics.consecutive_failures * 8)
            score -= penalty
        
        if metrics.sample_count > 0:
            success_rate = (metrics.success_count / metrics.sample_count) * 100
            if success_rate < 80:
                score -= (80 - success_rate) * 0.8
        
        return self._clamp_score(score)
    
    def _calculate_component_scores(self, metrics: QualityMetrics) -> Dict[str, float]:
        """Calculate individual component scores."""
        return {
            'packet_loss': round(self._score_packet_loss(metrics.packet_loss_percent)),
            'latency': round(self._score_latency(metrics.avg_latency_ms)),
            'jitter': round(self._score_jitter(metrics.jitter_ms)),
            'stability': round(self._score_stability(metrics))
        }
    
    def _calculate_weighted_score(self, component_scores: Dict[str, float]) -> float:
        """Calculate weighted total score."""
        total = (
            component_scores['packet_loss'] * self.thresholds.weight_packet_loss +
            component_scores['latency'] * self.thresholds.weight_latency +
            component_scores['jitter'] * self.thresholds.weight_jitter +
            component_scores['stability'] * self.thresholds.weight_stability
        )
        return self._clamp_score(total)
    
    def _determine_quality_level(self, score: float, metrics: QualityMetrics) -> QualityLevel:
        """Determine quality level based on score and critical indicators."""
        if metrics.packet_loss_percent >= self.thresholds.packet_loss_critical:
            return QualityLevel.CRITICAL
        if metrics.avg_latency_ms and metrics.avg_latency_ms >= self.thresholds.latency_critical:
            return QualityLevel.CRITICAL
        
        if score >= 70:
            return QualityLevel.GOOD
        elif score >= 40:
            return QualityLevel.DEGRADED
        elif score >= 20:
            return QualityLevel.POOR
        else:
            return QualityLevel.CRITICAL
    
    def _identify_issues(self, metrics: QualityMetrics) -> List[str]:
        """Identify specific issues affecting link quality."""
        issues = []
        
        if metrics.packet_loss_percent >= self.thresholds.packet_loss_critical:
            issues.append(f"Critical packet loss: {metrics.packet_loss_percent:.1f}%")
        elif metrics.packet_loss_percent >= self.thresholds.packet_loss_poor:
            issues.append(f"High packet loss: {metrics.packet_loss_percent:.1f}%")
        elif metrics.packet_loss_percent >= self.thresholds.packet_loss_degraded:
            issues.append(f"Packet loss: {metrics.packet_loss_percent:.1f}%")
        
        if metrics.avg_latency_ms:
            if metrics.avg_latency_ms >= self.thresholds.latency_critical:
                issues.append(f"Critical latency: {metrics.avg_latency_ms:.0f}ms")
            elif metrics.avg_latency_ms >= self.thresholds.latency_poor:
                issues.append(f"High latency: {metrics.avg_latency_ms:.0f}ms")
            elif metrics.avg_latency_ms >= self.thresholds.latency_degraded:
                issues.append(f"Elevated latency: {metrics.avg_latency_ms:.0f}ms")
        
        if metrics.jitter_ms:
            if metrics.jitter_ms >= self.thresholds.jitter_critical:
                issues.append(f"Critical jitter: {metrics.jitter_ms:.1f}ms")
            elif metrics.jitter_ms >= self.thresholds.jitter_poor:
                issues.append(f"High jitter: {metrics.jitter_ms:.1f}ms")
            elif metrics.jitter_ms >= self.thresholds.jitter_degraded:
                issues.append(f"Jitter: {metrics.jitter_ms:.1f}ms")
        
        if metrics.state_changes > self.thresholds.max_state_changes:
            issues.append(f"Unstable: {metrics.state_changes} state changes detected")
        if metrics.consecutive_failures >= self.thresholds.consecutive_failures_threshold:
            issues.append(f"Intermittent: {metrics.consecutive_failures} consecutive failures")
        
        return issues
    
    def _classify_degradation(self, metrics: QualityMetrics, issues: List[str]) -> DegradationType:
        """Classify the primary type of degradation by severity."""
        if not issues:
            return DegradationType.NONE
        
        severity_order = [
            DegradationType.NONE,
            DegradationType.HIGH_JITTER,
            DegradationType.HIGH_LATENCY,
            DegradationType.UNSTABLE,
            DegradationType.PACKET_LOSS,
            DegradationType.CRITICAL_LATENCY
        ]
        
        current_severity = DegradationType.NONE
        
        if metrics.packet_loss_percent >= self.thresholds.packet_loss_critical:
            current_severity = DegradationType.PACKET_LOSS
        elif metrics.avg_latency_ms and metrics.avg_latency_ms >= self.thresholds.latency_critical:
            current_severity = DegradationType.CRITICAL_LATENCY
        elif metrics.packet_loss_percent >= self.thresholds.packet_loss_poor:
            if severity_order.index(DegradationType.PACKET_LOSS) > severity_order.index(current_severity):
                current_severity = DegradationType.PACKET_LOSS
        elif metrics.state_changes > self.thresholds.max_state_changes:
            if severity_order.index(DegradationType.UNSTABLE) > severity_order.index(current_severity):
                current_severity = DegradationType.UNSTABLE
        elif metrics.avg_latency_ms and metrics.avg_latency_ms >= self.thresholds.latency_poor:
            if severity_order.index(DegradationType.HIGH_LATENCY) > severity_order.index(current_severity):
                current_severity = DegradationType.HIGH_LATENCY
        elif metrics.jitter_ms and metrics.jitter_ms >= self.thresholds.jitter_poor:
            if severity_order.index(DegradationType.HIGH_JITTER) > severity_order.index(current_severity):
                current_severity = DegradationType.HIGH_JITTER
        elif metrics.avg_latency_ms and metrics.avg_latency_ms >= self.thresholds.latency_degraded:
            if severity_order.index(DegradationType.HIGH_LATENCY) > severity_order.index(current_severity):
                current_severity = DegradationType.HIGH_LATENCY
        elif metrics.jitter_ms and metrics.jitter_ms >= self.thresholds.jitter_degraded:
            if severity_order.index(DegradationType.HIGH_JITTER) > severity_order.index(current_severity):
                current_severity = DegradationType.HIGH_JITTER
        
        if len(issues) >= 2 and current_severity == DegradationType.NONE:
            return DegradationType.MULTI_FACTOR
        
        return current_severity
    
    def analyze(self, metrics: QualityMetrics, current_status: Optional[str] = None) -> Dict:
        """Analyze link quality and return comprehensive assessment."""
        if current_status:
            metrics.state_changes = self.state_tracker.add_state(current_status)
        
        component_scores = self._calculate_component_scores(metrics)
        quality_score = self._calculate_weighted_score(component_scores)
        quality_level = self._determine_quality_level(quality_score, metrics)
        confidence = metrics.confidence
        issues = self._identify_issues(metrics)
        degradation_type = self._classify_degradation(metrics, issues)
        
        self.trend_analyzer.add_sample(quality_score, metrics.timestamp)
        
        trend = self.trend_analyzer.get_trend()
        volatility = self.trend_analyzer.get_volatility()
        early_warning = self.trend_analyzer.early_warning()
        
        result = {
            'quality_score': quality_score,
            'quality_level': quality_level.value,
            'confidence': round(confidence, 2),
            'issues': issues,
            'degradation_type': degradation_type.value,
            'component_scores': component_scores,
            'metrics': {
                'avg_latency_ms': metrics.avg_latency_ms,
                'jitter_ms': metrics.jitter_ms,
                'packet_loss_percent': round(metrics.packet_loss_percent, 1),
                'sample_count': metrics.sample_count,
                'consecutive_failures': metrics.consecutive_failures,
                'state_changes': metrics.state_changes
            }
        }
        
        if trend:
            result['trend'] = trend
        if volatility is not None:
            result['volatility'] = volatility
        if early_warning:
            result['early_warning'] = True
        
        return result
    
    def should_transition(self, proposed_level: str, required_cycles: int = 3) -> bool:
        """Determine if status should transition based on stability requirements."""
        return self.state_tracker.should_change_status(proposed_level, required_cycles)
    
    def is_flapping(self) -> bool:
        """Check if device is experiencing flapping."""
        return self.state_tracker.is_flapping()
    
    def reset(self):
        """Reset the analyzer state."""
        self.state_tracker.reset()
        self.trend_analyzer = TrendAnalyzer()