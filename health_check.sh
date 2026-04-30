#!/bin/bash

echo "========================================="
echo "     NetPulse Health Check"
echo "========================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check 1: Services
echo -e "\n1. Checking services..."
if systemctl is-active --quiet netpulse-api; then
    echo -e "   ${GREEN}✅ API Service is running${NC}"
else
    echo -e "   ${RED}❌ API Service is NOT running${NC}"
fi

if systemctl is-active --quiet netpulse-web; then
    echo -e "   ${GREEN}✅ Web Service is running${NC}"
else
    echo -e "   ${RED}❌ Web Service is NOT running${NC}"
fi

# Check 2: Ports
echo -e "\n2. Checking ports..."
if ss -tln | grep -q ":8000"; then
    echo -e "   ${GREEN}✅ Port 8000 (API) is listening${NC}"
else
    echo -e "   ${RED}❌ Port 8000 is NOT listening${NC}"
fi

if ss -tln | grep -q ":8080"; then
    echo -e "   ${GREEN}✅ Port 8080 (Web) is listening${NC}"
else
    echo -e "   ${RED}❌ Port 8080 is NOT listening${NC}"
fi

# Check 3: API Response
echo -e "\n3. Testing API endpoint..."
API_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)
if [ "$API_RESPONSE" = "200" ]; then
    echo -e "   ${GREEN}✅ API responds with HTTP 200${NC}"
else
    echo -e "   ${RED}❌ API returned HTTP $API_RESPONSE${NC}"
fi

# Check 4: Web Response
echo -e "\n4. Testing Web endpoint..."
WEB_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/)
if [ "$WEB_RESPONSE" = "200" ]; then
    echo -e "   ${GREEN}✅ Web server responds with HTTP 200${NC}"
else
    echo -e "   ${RED}❌ Web server returned HTTP $WEB_RESPONSE${NC}"
fi

# Check 5: Database
echo -e "\n5. Checking database..."
if [ -f "/home/kmtech/Projects/NetPulse/network-monitor/data/monitor.db" ]; then
    SIZE=$(du -h /home/kmtech/Projects/NetPulse/network-monitor/data/monitor.db | cut -f1)
    echo -e "   ${GREEN}✅ Database exists (size: $SIZE)${NC}"
else
    echo -e "   ${RED}❌ Database file not found${NC}"
fi

# Check 6: Latest Backup
echo -e "\n6. Checking backups..."
if [ -d "/home/kmtech/backups/netpulse" ]; then
    BACKUP_COUNT=$(ls -1 /home/kmtech/backups/netpulse/monitor.db.* 2>/dev/null | wc -l)
    if [ $BACKUP_COUNT -gt 0 ]; then
        echo -e "   ${GREEN}✅ Found $BACKUP_COUNT backup(s)${NC}"
        LATEST=$(ls -t /home/kmtech/backups/netpulse/monitor.db.* | head -1)
        echo -e "   ${GREEN}   Latest: $(basename $LATEST)${NC}"
    else
        echo -e "   ${YELLOW}⚠️  No backups found${NC}"
    fi
else
    echo -e "   ${YELLOW}⚠️  Backup directory not found${NC}"
fi

# Check 7: Environment
echo -e "\n7. Checking environment..."
if [ -f "/home/kmtech/Projects/NetPulse/network-monitor/.env" ]; then
    echo -e "   ${GREEN}✅ .env file exists${NC}"
else
    echo -e "   ${RED}❌ .env file missing${NC}"
fi

if [ -d "/home/kmtech/Projects/NetPulse/venv" ]; then
    echo -e "   ${GREEN}✅ Virtual environment exists${NC}"
else
    echo -e "   ${RED}❌ Virtual environment missing${NC}"
fi

echo -e "\n========================================="
echo "     Health Check Complete"
echo "========================================="
