#!/usr/bin/env python3
"""
Quality Metrics Module
NetPulse Network Monitoring System
"""

import statistics
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from ..utils.config import config


@dataclass
class QualityThresholds:
    """Quality thresholds for performance evaluation"""
    max_latency_ms: float = 300.0
    critical_latency_ms: float = 800.0
    max_jitter_ms: float = 150.0
    packet_loss_threshold: float = 10.0
    sample_window: int = 5


class QualityMetrics:
    """Track quality metrics with rolling window"""
    
    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self.samples: List[Dict] = []
        self.packet_loss_samples: List[bool] = []
    
    def add_multi_sample(self, ping_result):
        """Add a multi-ping sample"""
        self.samples.append({
            'timestamp': ping_result.timestamp,
            'is_reachable': ping_result.is_reachable,
            'avg_latency_ms': ping_result.avg_latency_ms,
            'min_latency_ms': ping_result.min_latency_ms,
            'max_latency_ms': ping_result.max_latency_ms,
            'packet_loss_percent': ping_result.packet_loss_percent
        })
        
        if len(self.samples) > self.window_size:
            self.samples.pop(0)
        
        self.packet_loss_samples.append(ping_result.is_reachable)
        if len(self.packet_loss_samples) > self.window_size:
            self.packet_loss_samples.pop(0)
    
    def add_sample(self, is_reachable: bool, latency_ms: Optional[float]):
        """Legacy method for single ping compatibility"""
        from .device import MultiPingResult
        ping_result = MultiPingResult(
            success_count=1 if is_reachable else 0,
            total_count=1,
            latencies=[latency_ms] if latency_ms else []
        )
        self.add_multi_sample(ping_result)
    
    @property
    def avg_latency(self) -> Optional[float]:
        """Average latency across samples"""
        latencies = [s['avg_latency_ms'] for s in self.samples 
                    if s['is_reachable'] and s['avg_latency_ms'] is not None]
        return statistics.mean(latencies) if latencies else None
    
    @property
    def max_latency(self) -> Optional[float]:
        """Maximum latency across samples"""
        latencies = [s['max_latency_ms'] for s in self.samples 
                    if s['is_reachable'] and s['max_latency_ms'] is not None]
        return max(latencies) if latencies else None
    
    @property
    def jitter(self) -> Optional[float]:
        """Calculate jitter (standard deviation of latency)"""
        latencies = [s['avg_latency_ms'] for s in self.samples 
                    if s['is_reachable'] and s['avg_latency_ms'] is not None]
        if len(latencies) >= 2:
            return statistics.stdev(latencies)
        return None
    
    @property
    def packet_loss_percentage(self) -> float:
        """Calculate packet loss percentage"""
        if not self.packet_loss_samples:
            return 0.0
        failures = sum(1 for s in self.packet_loss_samples if not s)
        return (failures / len(self.packet_loss_samples)) * 100.0
    
    @property
    def sample_count(self) -> int:
        return len(self.samples)
    
    def get_quality_score(self, thresholds: QualityThresholds) -> Dict:
        """
        Evaluate quality based on thresholds.
        Returns score from 0-100 with detailed metrics.
        """
        if self.sample_count < 2:
            return {
                'quality_score': None,
                'quality_level': 'Insufficient Data',
                'issues': ['Collecting data...'],
                'metrics': {}
            }
        
        issues = []
        quality_score = 100.0
        
        # Check packet loss
        packet_loss = self.packet_loss_percentage
        if packet_loss > thresholds.packet_loss_threshold:
            penalty = min(50, packet_loss * 2)
            quality_score -= penalty
            issues.append(f"Packet loss: {packet_loss:.1f}%")
        
        # Check latency
        avg_lat = self.avg_latency
        if avg_lat:
            if avg_lat > thresholds.critical_latency_ms:
                quality_score = min(quality_score, 30)
                issues.append(f"Critical latency: {avg_lat:.0f}ms")
            elif avg_lat > thresholds.max_latency_ms:
                excess = (avg_lat - thresholds.max_latency_ms) / thresholds.max_latency_ms
                penalty = min(40, excess * 40)
                quality_score -= penalty
                issues.append(f"High latency: {avg_lat:.0f}ms")
        
        # Check jitter
        jitter_val = self.jitter
        if jitter_val and jitter_val > thresholds.max_jitter_ms:
            excess = (jitter_val - thresholds.max_jitter_ms) / thresholds.max_jitter_ms
            penalty = min(30, excess * 30)
            quality_score -= penalty
            issues.append(f"High jitter: {jitter_val:.1f}ms")
        
        quality_score = max(0, min(100, quality_score))
        
        # Classify degradation type
        degradation_type = self._classify_degradation(issues)
        
        return {
            'quality_score': round(quality_score, 1),
            'quality_level': self._get_quality_level(quality_score),
            'issues': issues,
            'degradation_type': degradation_type,
            'metrics': {
                'avg_latency_ms': round(avg_lat, 1) if avg_lat else None,
                'jitter_ms': round(jitter_val, 1) if jitter_val else None,
                'packet_loss_percent': round(packet_loss, 1),
                'sample_count': self.sample_count
            }
        }
    
    def _classify_degradation(self, issues: List[str]) -> str:
        """Classify the type of degradation"""
        if not issues:
            return "none"
        
        issue_text = " ".join(issues).lower()
        
        if "packet loss" in issue_text:
            return "packet_loss"
        elif "critical latency" in issue_text:
            return "critical_latency"
        elif "high latency" in issue_text:
            return "high_latency"
        elif "jitter" in issue_text:
            return "jitter"
        else:
            return "unknown"
    
    def _get_quality_level(self, score: float) -> str:
        """Get quality level from score"""
        if score >= 70:
            return "Good"
        elif score >= 40:
            return "Degraded"
        else:
            return "Poor"