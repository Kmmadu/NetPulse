#!/bin/bash

# Register the first user for NetPulse

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}   NetPulse - First User Registration${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""

# Check if API is running
if ! curl -s http://localhost:8000/docs > /dev/null; then
    echo -e "${YELLOW}⚠️  API is not running. Starting NetPulse first...${NC}"
    echo "Please run: ./start.sh"
    exit 1
fi

read -p "Username: " username
read -p "Email: " email
read -s -p "Password (min 6 characters): " password
echo ""

# Register via API
response=$(curl -s -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$username\",\"email\":\"$email\",\"password\":\"$password\"}")

echo ""
if echo "$response" | grep -q "success"; then
    echo -e "${GREEN}✅ Registration successful!${NC}"
    echo -e "${GREEN}🔑 You can now login at: http://localhost:8080/login.html${NC}"
else
    echo -e "${YELLOW}❌ Registration failed: $response${NC}"
fi
