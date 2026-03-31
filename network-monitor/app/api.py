#!/usr/bin/env python3
"""
NetPulse REST API
FastAPI-based interface for web frontend - Clean JSON, no emojis
"""

import threading
import time
import sys
import os
from datetime import datetime
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from app.core.monitor_engine import MonitoringEngine
from app.models.device import Device, DeviceStatus
from app.auth import UserAuth
import secrets


# Global variables for monitoring thread
_monitoring_thread = None
_monitoring_active = False
_monitoring_interval = 30
_monitoring_engine = None

# Session storage (in production, use Redis or JWT)
sessions = {}


# ==================== Pydantic Models ====================

class DeviceCreate(BaseModel):
    """Model for creating a new device"""
    name: str = Field(..., description="Device name", example="Gateway")
    ip: str = Field(..., description="IP address", example="192.168.1.1")
    group: Optional[str] = Field("Default", description="Device group")


class DeviceUpdate(BaseModel):
    """Model for updating a device"""
    name: Optional[str] = Field(None, description="Device name")
    ip: Optional[str] = Field(None, description="IP address")
    group: Optional[str] = Field(None, description="Device group")


class DeviceResponse(BaseModel):
    """Model for device response - clean JSON, no emojis"""
    id: str
    name: str
    ip: str
    group: str
    status: str
    latency_ms: Optional[float] = None
    packet_loss_percent: float = 0.0
    avg_latency_ms: Optional[float] = None
    last_check: Optional[str] = None
    downtime_seconds: Optional[float] = None
    downtime_display: Optional[str] = None


class StatusResponse(BaseModel):
    """Overall system status"""
    total_devices: int
    devices_up: int
    devices_degraded: int
    devices_down: int
    devices_unknown: int
    last_update: str


class LogResponse(BaseModel):
    """Log entry response"""
    id: int
    device_id: str
    device_name: str
    timestamp: str
    status: str
    latency_ms: Optional[float] = None
    packet_loss_percent: float = 0.0


class MonitoringStatus(BaseModel):
    """Monitoring service status"""
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

def get_engine():
    """Get or create monitoring engine instance"""
    global _monitoring_engine
    if _monitoring_engine is None:
        _monitoring_engine = MonitoringEngine()
    return _monitoring_engine


def format_downtime(seconds: Optional[float]) -> Optional[str]:
    """Convert seconds to human-readable format"""
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
    """Convert device model to API response - with downtime tracking"""
    try:
        last_check = None
        if hasattr(device, '_last_check') and device._last_check:
            last_check = device._last_check.isoformat()
        
        downtime_seconds = None
        if hasattr(device, 'downtime_seconds') and device.downtime_seconds:
            downtime_seconds = device.downtime_seconds
        
        return DeviceResponse(
            id=device.device_id,
            name=device.name,
            ip=device.ip_address,
            group=getattr(device, 'device_group', 'Default'),
            status=device.status.value if device.status else "UNKNOWN",
            latency_ms=device._last_latency if hasattr(device, '_last_latency') else None,
            packet_loss_percent=0.0,
            avg_latency_ms=None,
            last_check=last_check,
            downtime_seconds=downtime_seconds,
            downtime_display=format_downtime(downtime_seconds)
        )
    except Exception as e:
        print(f"Error converting device: {e}")
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
            downtime_display=None
        )


def run_monitoring_loop(interval):
    """Background monitoring thread function"""
    global _monitoring_active
    
    engine = get_engine()
    
    while _monitoring_active:
        cycle_start = time.time()
        
        try:
            results = engine.check_all_devices()
            
            for result in results:
                if result.get('status_changed'):
                    status = result['current_status']
                    name = result['name']
                    if 'down' in result.get('transition_type', ''):
                        print(f"[Monitor] {name} is now DOWN")
                    elif 'up' in result.get('transition_type', ''):
                        downtime = result.get('downtime_seconds', 0)
                        if downtime:
                            mins = int(downtime / 60)
                            secs = int(downtime % 60)
                            print(f"[Monitor] {name} is back UP (was down for {mins}m {secs}s)")
                        else:
                            print(f"[Monitor] {name} is now UP")
            
        except Exception as e:
            print(f"[Monitor] Error: {e}")
        
        elapsed = time.time() - cycle_start
        sleep_time = max(0, interval - elapsed)
        if sleep_time > 0 and _monitoring_active:
            time.sleep(sleep_time)
    
    print("[Monitor] Monitoring stopped")


# ==================== FastAPI App ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    print("Starting NetPulse API...")
    get_engine()
    print(f"Loaded {len(get_engine().get_devices())} devices")
    yield
    print("Shutting down NetPulse API...")


app = FastAPI(
    title="NetPulse API",
    description="Network Monitoring System API",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Root Endpoint ====================

@app.get("/", tags=["Root"])
async def root():
    """API root endpoint"""
    return {
        "name": "NetPulse API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "devices": "/api/devices",
            "status": "/api/status",
            "history": "/api/history/{device_id}",
            "monitoring": "/api/monitoring/status",
            "auth": "/api/auth/register, /api/auth/login"
        }
    }


# ==================== Authentication Endpoints ====================

@app.post("/api/auth/register", tags=["Authentication"])
async def register(request: RegisterRequest):
    """Register a new user"""
    auth = UserAuth()
    user_id = auth.register(request.username, request.email, request.password)
    if user_id:
        token = secrets.token_urlsafe(32)
        sessions[token] = user_id
        return {"success": True, "token": token, "user_id": user_id}
    return {"success": False, "error": "Username or email already exists"}


@app.post("/api/auth/login", tags=["Authentication"])
async def login(request: LoginRequest):
    """Login user"""
    auth = UserAuth()
    user = auth.login(request.username, request.password)
    if user:
        token = secrets.token_urlsafe(32)
        sessions[token] = user['id']
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
    """Logout user"""
    if token in sessions:
        del sessions[token]
    return {"success": True}


# ==================== User Device Endpoints ====================

@app.get("/api/user/devices", tags=["User"])
async def get_user_devices(token: str):
    """Get devices for logged in user"""
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth = UserAuth()
    devices = auth.get_user_devices(sessions[token])
    return devices


@app.post("/api/user/devices", tags=["User"])
async def add_user_device(token: str, name: str, ip: str, group: str = "Default"):
    """Add device for user"""
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth = UserAuth()
    user_id = sessions[token]
    
    device_id = auth.add_user_device(user_id, name, ip, group)
    if device_id:
        return {"success": True, "device_id": device_id}
    return {"success": False, "error": "Device already exists"}


@app.put("/api/user/devices/{device_id}", tags=["User"])
async def update_user_device(token: str, device_id: str, name: str = None, ip: str = None, group: str = None):
    """Update user device"""
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth = UserAuth()
    if auth.update_user_device(sessions[token], device_id, name, ip, group):
        return {"success": True}
    return {"success": False}


@app.delete("/api/user/devices/{device_id}", tags=["User"])
async def delete_user_device(token: str, device_id: str):
    """Delete user device"""
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth = UserAuth()
    if auth.delete_user_device(sessions[token], device_id):
        return {"success": True}
    return {"success": False}


@app.get("/api/user/groups", tags=["User"])
async def get_user_groups(token: str):
    """Get groups for logged in user"""
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth = UserAuth()
    groups = auth.get_user_groups(sessions[token])
    return {"groups": groups}


@app.post("/api/user/alert-email", tags=["User"])
async def update_alert_email(token: str, alert_email: str):
    """Update user's alert email"""
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth = UserAuth()
    if auth.update_alert_email(sessions[token], alert_email):
        return {"success": True}
    return {"success": False}


# ==================== Device Endpoints (Legacy - will be replaced) ====================

@app.get("/api/devices", response_model=List[DeviceResponse], tags=["Devices (Legacy)"])
async def get_devices():
    """Get all monitored devices (legacy - will be replaced with user-specific)"""
    try:
        engine = get_engine()
        devices = engine.get_devices()
        return [_device_to_response(d) for d in devices]
    except Exception as e:
        print(f"Error in get_devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/{device_id}", response_model=DeviceResponse, tags=["Devices (Legacy)"])
async def get_device(device_id: str):
    """Get a specific device by ID (legacy)"""
    try:
        engine = get_engine()
        device = engine.devices.get(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
        return _device_to_response(device)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED, tags=["Devices (Legacy)"])
async def create_device(device: DeviceCreate):
    """Add a new device to monitor (legacy)"""
    try:
        engine = get_engine()
        
        for existing in engine.get_devices():
            if existing.ip_address == device.ip:
                raise HTTPException(status_code=400, detail=f"Device with IP {device.ip} already exists")
        
        device_id = device.name.lower().replace(' ', '_')
        new_device = Device(
            device_id=device_id,
            name=device.name,
            ip_address=device.ip,
            retry_count=2,
            max_latency_ms=200.0,
            packet_loss_threshold=10.0
        )
        
        if engine.add_device(new_device):
            return _device_to_response(new_device)
        else:
            raise HTTPException(status_code=500, detail="Failed to add device")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in create_device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/devices/{device_id}", response_model=DeviceResponse, tags=["Devices (Legacy)"])
async def update_device(device_id: str, updates: DeviceUpdate):
    """Update a device (legacy)"""
    try:
        engine = get_engine()
        
        if device_id not in engine.devices:
            raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
        
        update_dict = {}
        if updates.name:
            update_dict['name'] = updates.name
        if updates.ip:
            update_dict['ip_address'] = updates.ip
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        if engine.update_device(device_id, **update_dict):
            updated = engine.devices[device_id]
            return _device_to_response(updated)
        else:
            raise HTTPException(status_code=500, detail="Failed to update device")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in update_device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Devices (Legacy)"])
async def delete_device(device_id: str):
    """Remove a device from monitoring (legacy)"""
    try:
        engine = get_engine()
        
        if device_id not in engine.devices:
            raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
        
        if engine.remove_device(device_id):
            return None
        else:
            raise HTTPException(status_code=500, detail="Failed to delete device")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in delete_device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Status Endpoints ====================

@app.get("/api/status", response_model=StatusResponse, tags=["Monitoring"])
async def get_status():
    """Get overall monitoring status"""
    try:
        engine = get_engine()
        devices = engine.get_devices()
        
        up = sum(1 for d in devices if d.status == DeviceStatus.UP)
        degraded = sum(1 for d in devices if d.status == DeviceStatus.DEGRADED)
        down = sum(1 for d in devices if d.status == DeviceStatus.DOWN)
        unknown = sum(1 for d in devices if d.status == DeviceStatus.UNKNOWN)
        
        return StatusResponse(
            total_devices=len(devices),
            devices_up=up,
            devices_degraded=degraded,
            devices_down=down,
            devices_unknown=unknown,
            last_update=datetime.now().isoformat()
        )
    except Exception as e:
        print(f"Error in get_status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== History Endpoints ====================

@app.get("/api/history/{device_id}", response_model=List[LogResponse], tags=["Monitoring"])
async def get_device_history(device_id: str, limit: int = 100):
    """Get monitoring history for a device"""
    try:
        engine = get_engine()
        
        if device_id not in engine.devices:
            raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
        
        logs = engine.get_device_history(device_id, limit=limit)
        
        results = []
        device = engine.devices.get(device_id)
        device_name = device.name if device else device_id
        
        for log in logs:
            results.append(LogResponse(
                id=log.get('id', 0),
                device_id=device_id,
                device_name=device_name,
                timestamp=log.get('timestamp', ''),
                status=log.get('status', 'UNKNOWN'),
                latency_ms=log.get('latency_ms'),
                packet_loss_percent=log.get('packet_loss_percent', 0.0)
            ))
        
        return results
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_device_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history", response_model=List[LogResponse], tags=["Monitoring"])
async def get_all_history(limit: int = 100):
    """Get recent monitoring history across all devices"""
    try:
        engine = get_engine()
        
        changes = engine.get_state_changes(limit=limit)
        
        results = []
        for change in changes:
            device = engine.devices.get(change.get('device_id', ''))
            device_name = device.name if device else change.get('device_id', 'unknown')
            
            results.append(LogResponse(
                id=change.get('id', 0),
                device_id=change.get('device_id', 'unknown'),
                device_name=device_name,
                timestamp=change.get('timestamp', ''),
                status=change.get('to_status', 'UNKNOWN'),
                latency_ms=change.get('latency_ms'),
                packet_loss_percent=0.0
            ))
        
        return results
    except Exception as e:
        print(f"Error in get_all_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Monitoring Control Endpoints ====================

@app.post("/api/monitoring/start", response_model=MonitoringStatus, tags=["Monitoring Control"])
async def start_monitoring(interval: int = 30):
    """Start the background monitoring service"""
    global _monitoring_active, _monitoring_thread, _monitoring_interval
    
    if _monitoring_active:
        return MonitoringStatus(
            running=True,
            interval=_monitoring_interval,
            devices_count=len(get_engine().get_devices()),
            last_check=None
        )
    
    _monitoring_active = True
    _monitoring_interval = interval
    
    _monitoring_thread = threading.Thread(target=run_monitoring_loop, args=(interval,), daemon=True)
    _monitoring_thread.start()
    
    print(f"[API] Monitoring started with interval {interval}s")
    
    return MonitoringStatus(
        running=True,
        interval=interval,
        devices_count=len(get_engine().get_devices()),
        last_check=None
    )


@app.post("/api/monitoring/stop", response_model=MonitoringStatus, tags=["Monitoring Control"])
async def stop_monitoring():
    """Stop the background monitoring service"""
    global _monitoring_active
    
    _monitoring_active = False
    
    timeout = 5
    while _monitoring_thread and _monitoring_thread.is_alive() and timeout > 0:
        time.sleep(0.5)
        timeout -= 0.5
    
    print("[API] Monitoring stopped")
    
    return MonitoringStatus(
        running=False,
        interval=_monitoring_interval,
        devices_count=len(get_engine().get_devices()),
        last_check=None
    )


@app.get("/api/monitoring/status", response_model=MonitoringStatus, tags=["Monitoring Control"])
async def get_monitoring_status():
    """Get current monitoring service status"""
    global _monitoring_active, _monitoring_interval
    
    last_check = None
    try:
        engine = get_engine()
        devices = engine.get_devices()
        if devices:
            for device in devices:
                if hasattr(device, '_last_check') and device._last_check:
                    last_check = device._last_check.isoformat()
                    break
    except:
        pass
    
    return MonitoringStatus(
        running=_monitoring_active,
        interval=_monitoring_interval,
        devices_count=len(get_engine().get_devices()),
        last_check=last_check
    )


# ==================== Main Entry Point ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)