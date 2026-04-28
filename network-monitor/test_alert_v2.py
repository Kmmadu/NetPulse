#!/usr/bin/env python3
"""
Alert System Test Suite - NetPulse
Tests real alert scenarios: DOWN, RECOVERY, DUPLICATE PREVENTION, ERRATIC BEHAVIOR
"""

import sys
import os
import time
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.alert_v2 import AlertServiceV2


# Test device information
TEST_DEVICE_ID = "test-router-001"
TEST_DEVICE_NAME = "Test Core Router"
TEST_DEVICE_IP = "192.168.1.100"


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")


def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")


def print_info(message: str):
    """Print info message"""
    print(f"📢 {message}")


def print_warning(message: str):
    """Print warning message"""
    print(f"⚠️  {message}")


def cleanup_test_device():
    """Clean up any test data from previous runs"""
    db_path = "data/monitor.db"
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM alert_tracking WHERE device_id = ?", (TEST_DEVICE_ID,))
            cursor.execute("DELETE FROM device_state_history WHERE device_id = ?", (TEST_DEVICE_ID,))
            conn.commit()
            conn.close()
            print_info("Cleaned up previous test data")
        except Exception as e:
            print_warning(f"Cleanup warning: {e}")


def test_down_alert():
    """Test 1: Device DOWN alert"""
    print_section("TEST 1: DEVICE DOWN ALERT")
    
    alert = AlertServiceV2()
    
    print_info(f"Simulating {TEST_DEVICE_NAME} going from UP → DOWN")
    
    # Simulate device going DOWN - only 3 arguments (device_id, old_status, new_status)
    alert.process_status_change(TEST_DEVICE_ID, "UP", "DOWN")
    
    print_success("DOWN alert test completed")
    print_info("Check your email for: ALERT: Test Core Router is offline")


def test_recovery_alert():
    """Test 2: Device RECOVERY alert with downtime"""
    print_section("TEST 2: DEVICE RECOVERY ALERT")
    
    alert = AlertServiceV2()
    
    # First set device as DOWN
    print_info("Setting device to DOWN first...")
    alert.process_status_change(TEST_DEVICE_ID, "UP", "DOWN")
    time.sleep(1)
    
    print_info("Simulating device recovery after 120 seconds...")
    # Simulate device coming back UP
    alert.process_status_change(TEST_DEVICE_ID, "DOWN", "UP")
    
    print_success("Recovery alert test completed")
    print_info("Check your email for: RECOVERED: Test Core Router is back online")


def test_duplicate_prevention():
    """Test 3: Duplicate alert prevention (cooldown)"""
    print_section("TEST 3: DUPLICATE ALERT PREVENTION")
    
    alert = AlertServiceV2()
    
    print_info("First DOWN alert (should send email)...")
    alert.process_status_change(TEST_DEVICE_ID, "UP", "DOWN")
    
    print_info("Second DOWN alert (should be prevented by state tracking)...")
    alert.process_status_change(TEST_DEVICE_ID, "UP", "DOWN")
    
    print_success("Duplicate prevention test completed")
    print_info("Only ONE email should have been sent (second was blocked)")


def test_erratic_device():
    """Test 4: Erratic device detection (flapping)"""
    print_section("TEST 4: ERRATIC DEVICE DETECTION")
    
    alert = AlertServiceV2()
    
    # Clear previous state
    cleanup_test_device()
    
    time.sleep(1)
    
    print_info("Simulating rapid state changes (flapping)...")
    print_info("Sequence: UP → DOWN → UP → DOWN → UP")
    
    # Simulate rapid state changes - only 3 arguments
    changes = [
        ("UP", "DOWN"),
        ("DOWN", "UP"),
        ("UP", "DOWN"),
        ("DOWN", "UP"),
        ("UP", "DOWN"),
    ]
    
    for i, (old, new) in enumerate(changes, 1):
        print_info(f"  Change #{i}: {old} → {new}")
        alert.process_status_change(TEST_DEVICE_ID, old, new)
        time.sleep(0.5)
    
    print_success("Erratic device test completed")
    print_info("Monitor console for erratic behavior detection")


def test_degraded_alert():
    """Test 5: Degraded performance alert"""
    print_section("TEST 5: DEGRADED PERFORMANCE ALERT")
    
    alert = AlertServiceV2()
    
    print_info(f"Simulating {TEST_DEVICE_NAME} becoming DEGRADED")
    
    # First degraded alert (should send)
    alert.process_status_change(TEST_DEVICE_ID, "UP", "DEGRADED")
    
    print_info("Waiting 2 seconds...")
    time.sleep(2)
    
    print_info("Second degraded alert (same state - should be prevented)...")
    alert.process_status_change(TEST_DEVICE_ID, "UP", "DEGRADED")
    
    print_success("Degraded alert test completed")


def test_full_lifecycle():
    """Test 6: Complete device lifecycle (UP → DOWN → UP)"""
    print_section("TEST 6: COMPLETE DEVICE LIFECYCLE")
    
    alert = AlertServiceV2()
    
    cleanup_test_device()
    time.sleep(1)
    
    print_info("Phase 1: Device starts UP (normal operation)")
    print_info("Phase 2: Device goes DOWN")
    alert.process_status_change(TEST_DEVICE_ID, "UP", "DOWN")
    
    time.sleep(1)
    
    print_info("Phase 3: Device stays DOWN (no new alerts - same state)")
    alert.process_status_change(TEST_DEVICE_ID, "DOWN", "DOWN")
    
    time.sleep(1)
    
    print_info("Phase 4: Device recovers")
    alert.process_status_change(TEST_DEVICE_ID, "DOWN", "UP")
    
    print_success("Full lifecycle test completed")
    print_info("Expected: DOWN alert + RECOVERY alert")


def run_all_tests():
    """Run all alert system tests"""
    print("\n" + "🔥" * 35)
    print("     NETPULSE ALERT SYSTEM TEST SUITE")
    print("🔥" * 35)
    
    print_info("Testing real alert scenarios (not just email delivery)")
    print_info(f"Test device: {TEST_DEVICE_NAME} ({TEST_DEVICE_IP})")
    
    time.sleep(1)
    
    test_down_alert()
    time.sleep(2)
    
    test_recovery_alert()
    time.sleep(2)
    
    test_duplicate_prevention()
    time.sleep(2)
    
    test_erratic_device()
    time.sleep(2)
    
    test_degraded_alert()
    time.sleep(2)
    
    test_full_lifecycle()
    
    print_section("TEST SUMMARY")
    print_success("All tests completed!")
    print_info("What was tested:")
    print_info("  ✅ DOWN alert (device offline)")
    print_info("  ✅ RECOVERY alert")
    print_info("  ✅ Duplicate prevention (same state tracking)")
    print_info("  ✅ Erratic device detection (flapping)")
    print_info("  ✅ Degraded performance alert")
    print_info("  ✅ Complete device lifecycle")
    
    print("\n" + "📧" * 35)
    print("     Please check your email inbox for the actual alerts")
    print("📧" * 35)
    print()


def run_single_test(test_name: str):
    """Run a single test by name"""
    tests = {
        "down": test_down_alert,
        "recovery": test_recovery_alert,
        "duplicate": test_duplicate_prevention,
        "erratic": test_erratic_device,
        "degraded": test_degraded_alert,
        "lifecycle": test_full_lifecycle,
        "all": run_all_tests
    }
    
    if test_name in tests:
        tests[test_name]()
    else:
        print_error(f"Unknown test: {test_name}")
        print_info("Available tests: down, recovery, duplicate, erratic, degraded, lifecycle, all")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_single_test(sys.argv[1].lower())
    else:
        run_all_tests()
