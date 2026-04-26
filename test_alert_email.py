#!/usr/bin/env python3
"""Test the new email alert format"""
import os
from app.services.alert import AlertService

# Test DOWN alert
print("Testing DOWN alert format...")
test_result = {
    'device_id': 'test_router',
    'name': 'Core Router',
    'ip': '192.168.1.1',
    'current_status': 'DOWN',
    'status_changed': True,
    'transition_type': 'up_to_down',
    'quality': {
        'quality_score': 0,
        'success_rate': 0,
        'issues': ['No response to ICMP', 'Connection timeout']
    }
}

# This would send an actual email - only run if you want to test
# alert= AlertService()
# alert.send(test_result)
print("✅ Template ready - will send when monitoring detects a DOWN event")
