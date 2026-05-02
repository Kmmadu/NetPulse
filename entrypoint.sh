#!/bin/bash
# NetPulse Docker Entrypoint

set -e

echo "========================================="
echo "     NetPulse - Docker Container"
echo "========================================="

# Check if .env file exists, if not, use example
if [ ! -f /app/network-monitor/.env ]; then
    echo "⚠️  .env file not found, copying from example..."
    cp /app/network-monitor/.env.example /app/network-monitor/.env
    echo "✅ Please edit /app/network-monitor/.env with your SMTP settings"
fi

# Start API server in background
echo "🚀 Starting API server..."
cd /app/network-monitor
python api_run.py &
API_PID=$!

# Start web server
echo "🌐 Starting web server..."
cd /app/network-monitor/web
python -m http.server 8080 &
WEB_PID=$!

echo ""
echo "═══════════════════════════════════════════════════════"
echo "✅ NetPulse is running!"
echo "═══════════════════════════════════════════════════════"
echo "📍 Access NetPulse:"
echo "   🌐 Web Interface: http://localhost:8080"
echo "   📖 API Docs:      http://localhost:8000/docs"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "⚠️  Press Ctrl+C to stop all services"

# Wait for both processes
wait $API_PID $WEB_PID
