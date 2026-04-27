#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         NetPulse Network Monitor      ║${NC}"
echo -e "${GREEN}║         Starting Services...          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"

# Kill existing processes
echo -e "${YELLOW}Cleaning up existing processes...${NC}"
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:8080 | xargs kill -9 2>/dev/null

# Wait a moment
sleep 1

# Activate virtual environment
cd /home/kmtech/Projects/NetPulse
source venv/bin/activate

# Start API server in background
cd network-monitor
echo -e "${GREEN}🚀 Starting API server on port 8000...${NC}"
python api_run.py > /tmp/netpulse_api.log 2>&1 &
API_PID=$!

# Wait for API to start
sleep 3

# Start web server
cd web
echo -e "${GREEN}🌐 Starting Web server on port 8080...${NC}"
python3 -m http.server 8080 > /tmp/netpulse_web.log 2>&1 &
WEB_PID=$!

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ NetPulse is now running!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}📍 Access NetPulse:${NC}"
echo -e "   🌐 Landing Page: ${GREEN}http://localhost:8080/index.html${NC}"
echo -e "   🔑 Login Page:   ${GREEN}http://localhost:8080/login.html${NC}"
echo -e "   📊 Dashboard:    ${GREEN}http://localhost:8080/dashboard.html${NC}"
echo -e "   📖 API Docs:     ${GREEN}http://localhost:8000/docs${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}💡 Tip: Press Ctrl+C to stop all services${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down NetPulse...${NC}"
    kill $API_PID $WEB_PID 2>/dev/null
    echo -e "${GREEN}✅ Services stopped${NC}"
    exit 0
}

# Trap Ctrl+C
trap cleanup INT

# Wait for user to press Ctrl+C
wait
