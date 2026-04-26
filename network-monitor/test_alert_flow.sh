#!/bin/bash
echo "Testing NetPulse Alert Flow"
echo "=========================="

# Your current token (get from browser console)
TOKEN="gHCj3YGpHldocatiBx7hEJ4Ck6_wdWmJk44nT7k5yjU"

# Check alert emails configured
echo -e "\n1. Checking configured alert emails:"
curl -s "http://localhost:8000/api/user/alert-emails?token=$TOKEN" | python3 -m json.tool

# Send a test alert
echo -e "\n2. Sending test alert:"
curl -s -X POST "http://localhost:8000/api/user/alert-emails/test?token=$TOKEN" | python3 -m json.tool

# Check monitoring status
echo -e "\n3. Monitoring status:"
curl -s "http://localhost:8000/api/monitoring/status?token=$TOKEN" | python3 -m json.tool
