#!/bin/bash
# NetPulse Quick Setup Script

echo "========================================="
echo "     NetPulse Docker Setup"
echo "========================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed"
    echo "Please install Docker: https://docker.com"
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not available"
    exit 1
fi

# Create .env if not exists
if [ ! -f network-monitor/.env ]; then
    echo "📝 Creating .env file..."
    cp network-monitor/.env.example network-monitor/.env
    echo "⚠️  Please edit network-monitor/.env with your SMTP settings"
    echo "   Press Enter to continue after editing..."
    read
fi

# Start NetPulse
echo "🚀 Starting NetPulse..."
docker compose up -d

# Wait for services to start
sleep 5

echo ""
echo "✅ NetPulse is running!"
echo "📍 Access at: http://localhost:8080"
echo ""
echo "To stop: docker compose down"
echo "To view logs: docker compose logs -f"
