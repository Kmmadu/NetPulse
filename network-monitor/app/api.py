#!/usr/bin/env python3
"""
NetPulse REST API
FastAPI-based interface for web frontend - Clean JSON, no emojis
"""

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


# Pydantic Models for API (clean, no emojis)
class DeviceCreate(BaseModel):
    """Model for creating a new device"""
    name: str = Field(..., description="Device name", example="Gateway")
    ip: str = Field(..., description="IP address", example="192.168.1.1")


class DeviceUpdate(BaseModel):
    """Model for updating a device"""
    name: Optional[str] = Field(None, description="Device name")
    ip: Optional[str] = Field(None, description="IP address")


class DeviceResponse(BaseModel):
    """Model for device response - clean JSON, no emojis"""
    id: str
    name: str
    ip: str
    status: str  # "UP", "DEGRADED", "DOWN", "UNKNOWN"
    latency_ms: Optional[float] = None
    packet_loss_percent: float = 0.0
    avg_latency_ms: Optional[float] = None
    last_check: Optional[str] = None
    downtime_seconds: Optional[float] = None  # How long device has been down (if DOWN)
    downtime_display: Optional[str] = None    # Human-readable: "5m 30s", "2h 15m"


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


# Global engine variable
_monitoring_engine = None


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


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize monitoring engine
    print("Starting NetPulse API...")
    global _monitoring_engine
    _monitoring_engine = MonitoringEngine()
    print(f"Loaded {len(_monitoring_engine.get_devices())} devices")
    yield
    # Shutdown: Clean up if needed
    print("Shutting down NetPulse API...")


# Create FastAPI app
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


def _device_to_response(device) -> DeviceResponse:
    """Convert device model to API response - with downtime tracking"""
    try:
        # Get last check time
        last_check = None
        if hasattr(device, '_last_check') and device._last_check:
            last_check = device._last_check.isoformat()
        
        # Get downtime
        downtime_seconds = None
        if hasattr(device, 'downtime_seconds') and device.downtime_seconds:
            downtime_seconds = device.downtime_seconds
        
        return DeviceResponse(
            id=device.device_id,
            name=device.name,
            ip=device.ip_address,
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
            status="UNKNOWN",
            latency_ms=None,
            packet_loss_percent=0.0,
            avg_latency_ms=None,
            last_check=None,
            downtime_seconds=None,
            downtime_display=None
        )


# ==================== API Endpoints ====================

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
            "history": "/api/history/{device_id}"
        }
    }


@app.get("/api/devices", response_model=List[DeviceResponse], tags=["Devices"])
async def get_devices():
    """Get all monitored devices with downtime info"""
    try:
        engine = get_engine()
        devices = engine.get_devices()
        return [_device_to_response(d) for d in devices]
    except Exception as e:
        print(f"Error in get_devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/{device_id}", response_model=DeviceResponse, tags=["Devices"])
async def get_device(device_id: str):
    """Get a specific device by ID with downtime info"""
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


@app.post("/api/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED, tags=["Devices"])
async def create_device(device: DeviceCreate):
    """Add a new device to monitor"""
    try:
        engine = get_engine()
        
        # Check if device already exists by IP
        for existing in engine.get_devices():
            if existing.ip_address == device.ip:
                raise HTTPException(status_code=400, detail=f"Device with IP {device.ip} already exists")
        
        # Create device with defaults
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


@app.put("/api/devices/{device_id}", response_model=DeviceResponse, tags=["Devices"])
async def update_device(device_id: str, updates: DeviceUpdate):
    """Update a device (name and/or IP)"""
    try:
        engine = get_engine()
        
        if device_id not in engine.devices:
            raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
        
        # Prepare updates
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


@app.delete("/api/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Devices"])
async def delete_device(device_id: str):
    """Remove a device from monitoring"""
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
