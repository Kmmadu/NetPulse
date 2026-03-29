#!/usr/bin/env python3
"""
Base Models with Error Handling
NetPulse Network Monitoring System
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field


class ModelError(Exception):
    """Base exception for model errors"""
    pass


@dataclass
class BaseModel:
    """Base model with common functionality"""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def validate(self) -> bool:
        """Validate model data"""
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseModel':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class MetricsWindow:
    """Rolling window for metrics"""
    max_size: int = 10
    samples: List[Any] = field(default_factory=list)
    
    def add(self, value: Any):
        """Add sample to window"""
        self.samples.append(value)
        if len(self.samples) > self.max_size:
            self.samples.pop(0)
    
    def is_stable(self, required_samples: int = 3) -> bool:
        """Check if window has enough samples"""
        return len(self.samples) >= required_samples
    
    def clear(self):
        """Clear all samples"""
        self.samples.clear()
    
    @property
    def all(self) -> List[Any]:
        """Get all samples"""
        return self.samples.copy()
    
    @property
    def last(self) -> Optional[Any]:
        """Get last sample"""
        return self.samples[-1] if self.samples else None