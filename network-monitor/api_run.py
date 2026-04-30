#!/usr/bin/env python3
"""
Run NetPulse API Server - Production Version
"""

import uvicorn

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════╗
    ║         NetPulse API v1.0             ║
    ║    REST API for Network Monitor       ║
    ╚═══════════════════════════════════════╝
    """)
    print("🚀 Starting API server at http://localhost:8000")
    print("📖 Interactive docs: http://localhost:8000/docs")
    print("📋 API endpoints: /api/devices, /api/status, /api/history")
    print("Press Ctrl+C to stop\n")
    
    # reload=False for production (prevents double processes)
    uvicorn.run(
        "app.api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Critical: False for production
        workers=1      # Single worker for stability
    )
