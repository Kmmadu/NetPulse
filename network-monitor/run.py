#!/usr/bin/env python3
"""
NetPulse - Network Monitoring System
Main entry point
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli.main import main

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════╗
    ║         NetPulse v0.1.0               ║
    ║    Network Monitoring System          ║
    ╚═══════════════════════════════════════╝
    """)
    main()
