#!/usr/bin/env python3
"""
Configuration Management
NetPulse Network Monitoring System
"""

import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class MonitoringConfig:
    """Monitoring engine configuration"""
    check_interval: int = 5
    ping_count: int = 3  # Number of pings per check
    ping_timeout: int = 2
    ping_retry_delay: float = 0.5
    sample_window: int = 5
    quality_window: int = 5
    state_stability_cycles: int = 2  # Require N cycles before changing state


@dataclass
class QualityConfig:
    """Quality scoring thresholds"""
    up_threshold: float = 70.0
    degraded_threshold: float = 40.0
    down_threshold: float = 0.0
    
    # Default thresholds (can be overridden per device)
    default_max_latency_ms: float = 300.0
    default_critical_latency_ms: float = 800.0
    default_max_jitter_ms: float = 150.0
    default_packet_loss_threshold: float = 10.0


@dataclass
class AlertConfig:
    """Alerting configuration"""
    enabled: bool = True
    cooldown_seconds: int = 300  # 5 minutes
    group_alerts: bool = True
    alert_on_down: bool = True
    alert_on_degraded: bool = False  # Optional
    alert_on_recovery: bool = True


@dataclass
class DatabaseConfig:
    """Database configuration"""
    path: str = "data/monitor.db"
    backup_path: str = "data/backups/"
    retention_days: int = 30
    vacuum_on_startup: bool = False


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    file: Optional[str] = "logs/netpulse.log"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"


class Config:
    """Main configuration manager"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.monitoring = MonitoringConfig()
        self.quality = QualityConfig()
        self.alert = AlertConfig()
        self.database = DatabaseConfig()
        self.logging = LoggingConfig()
        
        if config_path and os.path.exists(config_path):
            self.load_from_file(config_path)
    
    def load_from_file(self, config_path: str):
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
                
            # Update monitoring config
            if 'monitoring' in data:
                for key, value in data['monitoring'].items():
                    if hasattr(self.monitoring, key):
                        setattr(self.monitoring, key, value)
            
            # Update quality config
            if 'quality' in data:
                for key, value in data['quality'].items():
                    if hasattr(self.quality, key):
                        setattr(self.quality, key, value)
            
            # Update alert config
            if 'alert' in data:
                for key, value in data['alert'].items():
                    if hasattr(self.alert, key):
                        setattr(self.alert, key, value)
            
            # Update database config
            if 'database' in data:
                for key, value in data['database'].items():
                    if hasattr(self.database, key):
                        setattr(self.database, key, value)
            
            # Update logging config
            if 'logging' in data:
                for key, value in data['logging'].items():
                    if hasattr(self.logging, key):
                        setattr(self.logging, key, value)
                        
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def save_to_file(self, config_path: str):
        """Save configuration to JSON file"""
        data = {
            'monitoring': self.monitoring.__dict__,
            'quality': self.quality.__dict__,
            'alert': self.alert.__dict__,
            'database': self.database.__dict__,
            'logging': self.logging.__dict__
        }
        
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'monitoring': self.monitoring.__dict__,
            'quality': self.quality.__dict__,
            'alert': self.alert.__dict__,
            'database': self.database.__dict__,
            'logging': self.logging.__dict__
        }


# Global config instance
config = Config()