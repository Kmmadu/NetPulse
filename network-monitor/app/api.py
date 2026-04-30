#!/usr/bin/env python3
"""
NetPulse REST API
FastAPI-based interface for web frontend - Clean JSON, no emojis
"""

import threading
import time
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
import secrets
import sqlite3
from datetime import datetime
from typing import List, Optional
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, status, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from contextlib import asynccontextmanager

from app.core.monitor_engine import MonitoringEngine
from app.models.device import Device, DeviceStatus
from app.auth import UserAuth
from app.services.alert_v2 import AlertServiceV2 as AlertService


# Session storage
_sessions = {}

# User-specific monitoring engines and threads
_monitoring_engines = {}
_monitoring_threads = {}
_monitoring_active = {}
_monitoring_intervals = {}


# ==================== Pydantic Models ====================

class DeviceCreate(BaseModel):
    name: str
    ip: str


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None


class DeviceResponse(BaseModel):
    id: str
    name: str
    ip: str
    group: str = "Default"
    status: str
    latency_ms: Optional[float] = None
    packet_loss_percent: float = 0.0
    avg_latency_ms: Optional[float] = None
    last_check: Optional[str] = None
    downtime_seconds: Optional[float] = None
    downtime_display: Optional[str] = None
    quality_score: Optional[int] = None
    quality_level: Optional[str] = None
    jitter_ms: Optional[float] = None


class StatusResponse(BaseModel):
    total_devices: int
    devices_up: int
    devices_degraded: int
    devices_down: int
    devices_unknown: int
    last_update: str


class LogResponse(BaseModel):
    id: int
    device_id: str
    device_name: str
    timestamp: str
    status: str
    latency_ms: Optional[float] = None
    packet_loss_percent: float = 0.0
    quality_score: Optional[int] = None


class MonitoringStatus(BaseModel):
    running: bool
    interval: int
    devices_count: int
    last_check: Optional[str] = None


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


# ==================== Helper Functions ====================

def get_engine_for_user(user_id: int):
    global _monitoring_engines
    if user_id not in _monitoring_engines:
        _monitoring_engines[user_id] = MonitoringEngine(user_id=user_id, max_workers=10)
    return _monitoring_engines[user_id]


def format_downtime(seconds: Optional[float]) -> Optional[str]:
    if not seconds:
        return None
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        remaining_seconds = int(seconds % 60)
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"
    else:
        hours = int(seconds / 3600)
        remaining_minutes = int((seconds % 3600) / 60)
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"


def _device_to_response(device) -> DeviceResponse:
    try:
        last_check = None
        if hasattr(device, '_last_check') and device._last_check:
            last_check = device._last_check.isoformat()
        
        downtime_seconds = None
        if hasattr(device, 'downtime_seconds') and device.downtime_seconds:
            downtime_seconds = device.downtime_seconds
        
        device_group = getattr(device, 'device_group', 'Default')
        
        return DeviceResponse(
            id=device.device_id,
            name=device.name,
            ip=device.ip_address,
            group=device_group,
            status=device.status.value if device.status else "UNKNOWN",
            latency_ms=device._last_latency if hasattr(device, '_last_latency') else None,
            packet_loss_percent=0.0,
            avg_latency_ms=None,
            last_check=last_check,
            downtime_seconds=downtime_seconds,
            downtime_display=format_downtime(downtime_seconds),
            quality_score=None,
            quality_level=None,
            jitter_ms=None
        )
    except Exception as e:
        return DeviceResponse(
            id=getattr(device, 'device_id', 'unknown'),
            name=getattr(device, 'name', 'unknown'),
            ip=getattr(device, 'ip_address', 'unknown'),
            group="Default",
            status="UNKNOWN",
            latency_ms=None,
            packet_loss_percent=0.0,
            avg_latency_ms=None,
            last_check=None,
            downtime_seconds=None,
            downtime_display=None,
            quality_score=None,
            quality_level=None,
            jitter_ms=None
        )


def run_monitoring_loop(user_id: int, interval: int):
    global _monitoring_active
    engine = get_engine_for_user(user_id)
    
    # Get user's alert email once at the start (for reference only, V2 uses .env)
    conn = sqlite3.connect("data/monitor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT alert_email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    alert_emails = row[0].split(',') if row and row[0] else []
    conn.close()
    
    print(f"[Monitor] Monitoring started for user {user_id}")
    print(f"[Monitor] Alert emails: {alert_emails}")
    
    # Create alert service once (V2 reads config from .env)
    alert_service = AlertService()
    
    while _monitoring_active.get(user_id, False):
        cycle_start = time.time()
        try:
            results = engine.check_all_devices()
            for result in results:
                if result.get('status_changed'):
                    old_status = result.get('previous_status', 'UNKNOWN')
                    new_status = result.get('current_status', 'UNKNOWN')
                    device_id = result.get('device_id')
                    print(f"[Monitor] Status changed for {result.get('name')}: {old_status} → {new_status}")
                    alert_service.process_status_change(device_id, old_status, new_status)
        except Exception as e:
            print(f"Monitor error: {e}")
        
        elapsed = time.time() - cycle_start
        sleep_time = max(0, interval - elapsed)
        if sleep_time > 0 and _monitoring_active.get(user_id, False):
            time.sleep(sleep_time)


# ==================== FastAPI App ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting NetPulse API...")
    yield
    print("Shutting down NetPulse API...")


app = FastAPI(title="NetPulse API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
async def root():
    return {"name": "NetPulse API", "status": "running"}


@app.post("/api/auth/register", tags=["Authentication"])
async def register(request: RegisterRequest):
    auth = UserAuth()
    user_id = auth.register(request.username, request.email, request.password)
    if user_id:
        token = secrets.token_urlsafe(32)
        _sessions[token] = user_id
        return {"success": True, "token": token, "user_id": user_id}
    return {"success": False, "error": "Username or email already exists"}


@app.post("/api/auth/login", tags=["Authentication"])
async def login(request: LoginRequest):
    auth = UserAuth()
    user = auth.login(request.username, request.password)
    if user:
        token = secrets.token_urlsafe(32)
        _sessions[token] = user['id']
        return {
            "success": True,
            "token": token,
            "user_id": user['id'],
            "username": user['username'],
            "alert_email": user.get('alert_email')
        }
    return {"success": False, "error": "Invalid credentials"}


@app.post("/api/auth/logout", tags=["Authentication"])
async def logout(token: str):
    if token in _sessions:
        del _sessions[token]
    return {"success": True}


@app.get("/api/user/alert-emails", tags=["User"])
async def get_alert_emails(token: str):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    
    conn = sqlite3.connect("data/monitor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT alert_email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    alert_emails = row[0].split(',') if row and row[0] else []
    return {"alert_emails": alert_emails}


@app.post("/api/user/alert-email", tags=["User"])
async def update_alert_email(token: str = Query(...), alert_email: str = Query(...)):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_id = _sessions[token]
    
    conn = sqlite3.connect("data/monitor.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET alert_email = ? WHERE id = ?", (alert_email, user_id))
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "Alert email updated successfully"}


@app.delete("/api/user/alert-email", tags=["User"])
async def remove_alert_email(token: str = Query(...), alert_email: str = Query(...)):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_id = _sessions[token]
    
    conn = sqlite3.connect("data/monitor.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET alert_email = NULL WHERE id = ? AND alert_email = ?", (user_id, alert_email))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if affected > 0:
        return {"success": True, "message": f"Alert email {alert_email} removed successfully"}
    return {"success": False, "message": "Email not found"}


@app.post("/api/user/alert-emails/test", tags=["User"])
async def test_alert_email(token: str):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    
    conn = sqlite3.connect("data/monitor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT alert_email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    alert_emails = row[0].split(',') if row and row[0] else []
    
    if not alert_emails:
        raise HTTPException(status_code=400, detail="No alert emails configured")
    
    alert_service = AlertService()
    if alert_service.send_test_alert():
        return {"success": True, "message": "Test alert sent"}
    raise HTTPException(status_code=500, detail="Failed to send test alert")


@app.get("/api/user/devices", tags=["User"])
async def get_user_devices(token: str):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    auth = UserAuth()
    user_devices = auth.get_user_devices(user_id)
    
    engine = get_engine_for_user(user_id)
    result = []
    
    for device_data in user_devices:
        device_id = device_data['device_id']
        if device_id in engine.devices:
            device = engine.devices[device_id]
            device.device_group = device_data.get('device_group', 'Default')
            result.append(_device_to_response(device))
        else:
            new_device = Device(
                device_id=device_id,
                name=device_data['name'],
                ip_address=device_data['ip_address'],
                retry_count=device_data.get('retry_count', 2),
                timeout=2,
                max_latency_ms=device_data.get('max_latency_ms', 200.0),
                packet_loss_threshold=device_data.get('packet_loss_threshold', 10.0)
            )
            new_device.device_group = device_data.get('device_group', 'Default')
            engine.devices[device_id] = new_device
            result.append(_device_to_response(new_device))
    
    return result


@app.post("/api/user/devices", tags=["User"])
async def add_user_device(token: str, name: str, ip: str, group: str = "Default"):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    auth = UserAuth()
    device_id = auth.add_user_device(user_id, name, ip, group)
    
    if device_id:
        engine = get_engine_for_user(user_id)
        new_device = Device(device_id=device_id, name=name, ip_address=ip, retry_count=2, max_latency_ms=200.0, packet_loss_threshold=10.0)
        new_device.device_group = group
        engine.devices[device_id] = new_device
        return {"success": True, "device_id": device_id}
    return {"success": False, "error": "Device already exists"}


@app.put("/api/user/devices/{device_id}", tags=["User"])
async def update_user_device(token: str, device_id: str, name: str = None, ip: str = None, group: str = None):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    auth = UserAuth()
    
    # Get old device info before update
    engine = get_engine_for_user(user_id)
    old_ip = None
    old_status = "UNKNOWN"
    
    if device_id in engine.devices:
        old_ip = engine.devices[device_id].ip_address
        old_status = engine.devices[device_id].status.value if engine.devices[device_id].status else "UNKNOWN"
    
    if auth.update_user_device(user_id, device_id, name, ip, group):
        if device_id in engine.devices:
            device = engine.devices[device_id]
            
            # Track what changed
            ip_changed = ip is not None and old_ip != ip
            
            if name:
                device.name = name
            if ip:
                device.ip_address = ip
            if group:
                device.device_group = group
            
            # CRITICAL FIX: If IP changed, reset device state to force re-evaluation
            if ip_changed:
                print(f"\n[API] 🔄 IP changed for {device.name}: {old_ip} → {ip}")
                print(f"[API] Old status was {old_status}, resetting device state")
                
                # Reset device state
                device._fail_count = 0
                device._status = DeviceStatus.UNKNOWN
                device._down_since = None
                device._degraded_since = None
                device._initial_alert_sent = False
                
                # Also clear in database
                try:
                    with sqlite3.connect("data/monitor.db") as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE devices 
                            SET status = 'UNKNOWN', down_since = NULL, initial_alert_sent = 0
                            WHERE device_id = ?
                        """, (device_id,))
                        conn.commit()
                    print(f"[API] ✅ Reset database state for {device.name}")
                except Exception as e:
                    print(f"[API] ⚠️ Failed to reset device in DB: {e}")
        
        return {"success": True, "message": "Device updated"}
    return {"success": False, "error": "Device not found"}


@app.delete("/api/user/devices/{device_id}", tags=["User"])
async def delete_user_device(token: str, device_id: str):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    auth = UserAuth()
    
    if auth.delete_user_device(user_id, device_id):
        engine = get_engine_for_user(user_id)
        if device_id in engine.devices:
            del engine.devices[device_id]
        return {"success": True, "message": "Device deleted"}
    return {"success": False, "error": "Device not found"}


@app.post("/api/monitoring/start", response_model=MonitoringStatus, tags=["Monitoring Control"])
async def start_monitoring(token: str, interval: int = 30):
    global _monitoring_active, _monitoring_threads, _monitoring_intervals
    
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    
    if _monitoring_active.get(user_id, False):
        return MonitoringStatus(running=True, interval=_monitoring_intervals.get(user_id, interval), devices_count=len(get_engine_for_user(user_id).get_devices()), last_check=None)
    
    engine = get_engine_for_user(user_id)
    devices = engine.get_devices()
    
    if not devices:
        raise HTTPException(status_code=400, detail="No devices configured")
    
    _monitoring_active[user_id] = True
    _monitoring_intervals[user_id] = interval
    
    _monitoring_threads[user_id] = threading.Thread(target=run_monitoring_loop, args=(user_id, interval), daemon=True)
    _monitoring_threads[user_id].start()
    
    return MonitoringStatus(running=True, interval=interval, devices_count=len(devices), last_check=None)


@app.post("/api/monitoring/stop", response_model=MonitoringStatus, tags=["Monitoring Control"])
async def stop_monitoring(token: str):
    global _monitoring_active
    
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    
    if user_id in _monitoring_active:
        _monitoring_active[user_id] = False
    
    return MonitoringStatus(running=False, interval=_monitoring_intervals.get(user_id, 30), devices_count=len(get_engine_for_user(user_id).get_devices()), last_check=None)


@app.get("/api/monitoring/status", response_model=MonitoringStatus, tags=["Monitoring Control"])
async def get_monitoring_status(token: str):
    if token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = _sessions[token]
    engine = get_engine_for_user(user_id)
    devices = engine.get_devices()
    
    return MonitoringStatus(
        running=_monitoring_active.get(user_id, False),
        interval=_monitoring_intervals.get(user_id, 30),
        devices_count=len(devices),
        last_check=None
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
@app.get("/api/debug/users", tags=["Debug"])
async def debug_users():
    import sqlite3
    conn = sqlite3.connect("data/monitor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email FROM users")
    users = cursor.fetchall()
    conn.close()
    return {"users": [{"id": u[0], "username": u[1], "email": u[2]} for u in users]}
