#!/usr/bin/env python3
"""Test database functionality"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import Database

def test_database():
    """Test database operations"""
    print("Testing NetPulse Database...")
    print("="*50)
    
    # Initialize database
    db = Database("data/test.db")
    print("✅ Database initialized")
    
    # Add devices
    print("\n📝 Adding devices...")
    db.add_device("gw1", "Gateway", "10.3.104.2", retry_count=2)
    db.add_device("dns1", "Google DNS", "8.8.8.8", retry_count=1)
    db.add_device("airtel1", "Airtel Ikeja", "10.2.104.6", retry_count=1)
    print("✅ Devices added")
    
    # List devices
    print("\n📋 Device list:")
    devices = db.get_all_devices()
    for device in devices:
        print(f"  {device['device_id']}: {device['name']} ({device['ip_address']})")
    
    # Add logs
    print("\n📊 Adding test logs...")
    from datetime import datetime
    
    logs = [
        {'device_id': 'gw1', 'timestamp': datetime.now(), 'is_reachable': True, 
         'latency_ms': 10.5, 'fail_count': 0, 'retry_count': 2, 
         'status': 'UP', 'status_changed': True, 'transition_type': 'initial_up'},
        
        {'device_id': 'dns1', 'timestamp': datetime.now(), 'is_reachable': False,
         'latency_ms': None, 'fail_count': 1, 'retry_count': 1,
         'status': 'DOWN', 'status_changed': True, 'transition_type': 'up_to_down'},
        
        {'device_id': 'airtel1', 'timestamp': datetime.now(), 'is_reachable': True,
         'latency_ms': 25.3, 'fail_count': 0, 'retry_count': 1,
         'status': 'UP', 'status_changed': True, 'transition_type': 'down_to_up'},
    ]
    
    for log in logs:
        db.add_log(log)
    
    # Add state changes
    changes = [
        {'device_id': 'gw1', 'timestamp': datetime.now(), 'from_status': None,
         'to_status': 'UP', 'transition_type': 'initial_up', 'latency_ms': 10.5},
        
        {'device_id': 'dns1', 'timestamp': datetime.now(), 'from_status': 'UP',
         'to_status': 'DOWN', 'transition_type': 'up_to_down', 'latency_ms': None},
        
        {'device_id': 'airtel1', 'timestamp': datetime.now(), 'from_status': 'DOWN',
         'to_status': 'UP', 'transition_type': 'down_to_up', 'latency_ms': 25.3},
    ]
    
    for change in changes:
        db.add_state_change(change)
    
    print("✅ Logs and state changes added")
    
    # Query statistics
    print("\n📈 Uptime stats:")
    stats = db.get_uptime_stats('gw1', days=7)
    if stats:
        print(f"  Gateway: {stats['uptime_percentage']}% uptime")
    
    # Database stats
    db_stats = db.get_database_stats()
    print(f"\n💾 Database stats:")
    print(f"  Devices: {db_stats['device_count']}")
    print(f"  Logs: {db_stats['log_count']}")
    print(f"  State changes: {db_stats['state_change_count']}")
    print(f"  Size: {db_stats.get('db_size_mb', 0)} MB")
    
    print("\n✅ Database test complete!")

if __name__ == "__main__":
    test_database()
