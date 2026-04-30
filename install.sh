#!/bin/bash
# NetPulse Production Installer
# One-command setup for systemd auto-start and backups

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              NetPulse Production Installer               ║"
echo "║         Auto-Start + Backup Configuration                ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Detect Python path
PYTHON_PATH=$(which python3)
VENV_PATH="$SCRIPT_DIR/venv/bin/python"

if [ -f "$VENV_PATH" ]; then
    PYTHON_EXEC="$VENV_PATH"
    echo -e "${GREEN}✅ Found virtual environment at: $VENV_PATH${NC}"
else
    PYTHON_EXEC="$PYTHON_PATH"
    echo -e "${YELLOW}⚠️  Virtual environment not found, using system Python: $PYTHON_PATH${NC}"
fi

# Detect user
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)

echo -e "${BLUE}📋 Configuration:${NC}"
echo "   User: $CURRENT_USER"
echo "   Group: $CURRENT_GROUP"
echo "   Python: $PYTHON_EXEC"
echo "   Install Dir: $SCRIPT_DIR"

# Create systemd service files
echo -e "\n${BLUE}🔧 Creating systemd service files...${NC}"

# API Service
sudo tee /etc/systemd/system/netpulse-api.service > /dev/null << EOF
[Unit]
Description=NetPulse API Server
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$SCRIPT_DIR/network-monitor
Environment="PATH=$SCRIPT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$PYTHON_EXEC $SCRIPT_DIR/network-monitor/api_run.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=netpulse-api

[Install]
WantedBy=multi-user.target
