#!/usr/bin/env python3
"""
Device Model - Core device state management
NetPulse Network Monitoring System
"""

from datetime import datetime
from typing import Dict, Optional
import json


class Device:
    """
    Represents a network device with its monitoring state.
    Handles all state transitions and retry logic.
    
    This is the heart of the monitoring system - it maintains
    the state machine for each device being monitored.
    """
    
    def __init__(self, device_id: str, name: str, ip_address: str, 
                 retry_count: int = 2, timeout: int = 2):
        """
        Initialize a device monitor
        
        Args:
            device_id: Unique identifier (used as primary key)
            name: Human-readable display name
            ip_address: IPv4 address to monitor
            retry_count: Number of consecutive failures before marking DOWN
            timeout: Ping timeout in seconds
        """
        # Configuration (immutable except through update methods)
        self.device_id = device_id
        self.name = name
        self.ip_address = ip_address
        self.retry_count = max(1, retry_count)  # Minimum 1 retry
        self.timeout = max(1, timeout)  # Minimum 1 second timeout
        
        # Runtime state (tracked in memory)
        self._current_status = None  # None=unknown, True=UP, False=DOWN
        self._previous_status = None
        self._fail_count = 0  # Current consecutive failures
        self._last_check_time = None
        self._last_latency = None
        self._last_state_change = None
        
    @property
    def status(self) -> Optional[bool]:
        """Current status: True=UP, False=DOWN, None=Unknown"""
        return self._current_status
    
    @property
    def status_text(self) -> str:
        """Human-readable status"""
        if self._current_status is True:
            return "UP"
        elif self._current_status is False:
            return "DOWN"
        else:
            return "UNKNOWN"
    
    @property
    def previous_status(self) -> Optional[bool]:
        """Previous status before last state change"""
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
    def uptime_percentage(self) -> Optional[float]:
        """Calculate uptime percentage (placeholder - will use DB history later)"""
        # This will be implemented when we have historical data
        return None
    
    def process_check_result(self, is_reachable: bool, latency: Optional[float] = None) -> Dict:
        """
        Process a single check result and update device state.
        
        This is the core state machine logic:
        - Successful ping: Reset failure counter, mark as UP
        - Failed ping: Increment failure counter
        - Mark DOWN only after retry_count consecutive failures
        - Track state changes for alerting
        
        Args:
            is_reachable: True if ping succeeded, False otherwise
            latency: Response time in ms (if reachable)
            
        Returns:
            Dict with complete check result including any state change
        """
        # Record check metadata
        self._last_check_time = datetime.now()
        self._last_latency = latency if is_reachable else None
        
        # Track state before update
        old_status = self._current_status
        status_changed = False
        new_status = None
        
        # Update state machine based on check result
        if is_reachable:
            # Success! Reset everything
            self._fail_count = 0
            new_status = True
        else:
            # Failure: increment counter
            self._fail_count += 1
            
            # Determine if we should mark as DOWN
            if self._fail_count >= self.retry_count:
                new_status = False
            else:
                # Not enough failures yet, maintain current status
                new_status = self._current_status
        
        # Handle initial unknown state and transitions
        if new_status is not None and new_status != self._current_status:
            # Status change detected
            status_changed = True
            self._previous_status = self._current_status
            self._current_status = new_status
            self._last_state_change = self._last_check_time
        elif self._current_status is None and new_status is not None:
            # First definitive status (initial check)
            status_changed = True
            self._previous_status = None
            self._current_status = new_status
            self._last_state_change = self._last_check_time
        else:
            # No change, keep current status
            pass
        
        # Prepare structured result for logging/database
        result = {
            'device_id': self.device_id,
            'name': self.name,
            'ip': self.ip_address,
            'timestamp': self._last_check_time,
            'is_reachable': is_reachable,
            'latency_ms': latency if is_reachable else None,
            'fail_count': self._fail_count,
            'retry_count': self.retry_count,
            'current_status': self._current_status,
            'status_text': self.status_text,
            'status_changed': status_changed,
            'old_status': old_status,
            'new_status': new_status if status_changed else None,
            'transition_type': self._get_transition_type(old_status, new_status) if status_changed else None
        }
        
        return result
    
    def _get_transition_type(self, old: Optional[bool], new: Optional[bool]) -> Optional[str]:
        """Determine the type of state transition"""
        if old is None and new is True:
            return "initial_up"
        elif old is None and new is False:
            return "initial_down"
        elif old is True and new is False:
            return "up_to_down"
        elif old is False and new is True:
            return "down_to_up"
        return None
    
    def reset(self):
        """Reset device state (useful when starting fresh)"""
        self._current_status = None
        self._previous_status = None
        self._fail_count = 0
        self._last_check_time = None
        self._last_latency = None
        self._last_state_change = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for database storage"""
        return {
            'id': self.device_id,
            'name': self.name,
            'ip_address': self.ip_address,
            'retry_count': self.retry_count,
            'timeout': self.timeout,
            'created_at': datetime.now().isoformat()  # Will be set by DB
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    def __repr__(self) -> str:
        return f"Device(id={self.device_id}, name={self.name}, ip={self.ip_address}, status={self.status_text}, fails={self._fail_count}/{self.retry_count})"
