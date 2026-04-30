#!/bin/bash

echo "=== NetPulse Connection Diagnosis ==="
echo ""

echo "1. Testing API locally:"
curl -s http://localhost:8000/ && echo " - OK" || echo " - FAILED"

echo ""
echo "2. Testing API with curl:"
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"Swift","password":"test"}' | head -c 200
echo ""

echo ""
echo "3. Checking processes:"
ps aux | grep -E "api_run|http.server" | grep -v grep

echo ""
echo "4. Checking ports:"
ss -tlnp | grep -E "8000|8080"

echo ""
echo "5. Checking firewall:"
sudo ufw status 2>/dev/null || echo "UFW not installed"

echo ""
echo "6. API logs (last 10 lines):"
sudo journalctl -u netpulse-api -n 10 --no-pager 2>/dev/null || echo "No systemd logs"
