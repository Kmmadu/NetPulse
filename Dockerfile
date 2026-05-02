# NetPulse Dockerfile - Cross-platform container
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY network-monitor/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the entire application
COPY network-monitor/ /app/network-monitor/
COPY scripts/ /app/scripts/

# Create data directory for persistence
RUN mkdir -p /app/network-monitor/data

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose ports
EXPOSE 8000 8080

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]
