# NetPulse - Docker Deployment

Run NetPulse on any platform (Windows, Mac, Linux) with Docker.

## Prerequisites

- Docker installed: https://docker.com
- Docker Compose (included with Docker Desktop)

## Quick Start (5 minutes)

### 1. Clone the repository

```bash
git clone https://github.com/Kmmadu/NetPulse.git
cd NetPulse
```

---

### 2. Configure email settings

# Copy the example config
cp network-monitor/.env.example network-monitor/.env

# Edit .env with your SMTP settings
nano network-monitor/.env  # or use any text editor

---

### 3. Start NetPulse

```bash 
docker-compose up -d
```

---

### 4. Access NetPulse

# Open your browser: http://localhost:8080

* Web Interface: http://localhost:8080
* API Docs: http://localhost:8000/docs

---

### 5. Create your account

* Click "Register"
* Create your username and password
* Login to dashboard
* Start monitoring!

## Platform-Specific Instructions
# Windows (PowerShell)

```bash 
# Clone repository
git clone https://github.com/Kmmadu/NetPulse.git
cd NetPulse

# Start NetPulse
docker-compose up -d

# View logs
docker-compose logs -f

```
# macOS / Linux
```bash 
# Same commands work everywhere!
git clone https://github.com/Kmmadu/NetPulse.git
cd NetPulse
docker-compose up -d
```

# Common Commands

```bash
# Start NetPulse
docker-compose up -d

# Stop NetPulse
docker-compose down

# View logs
docker-compose logs -f

# Restart
docker-compose restart

# Update to latest version
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d

```

## Configuration

# Email Setup (Required)
Edit network-monitor/.env:

```bash
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_TO=alerts@yourdomain.com

```

# Getting a Gmail App Password

* Enable 2FA on your Google account
* Go to https://myaccount.google.com/apppasswords
* Generate App Password for NetPulse
* Copy the 16-character password

# Data Persistence

Your database is stored in the ./data directory. Back up this directory to save your monitoring data.

``` bash
# Backup
tar -czf netpulse-backup.tar.gz data/

# Restore
tar -xzf netpulse-backup.tar.gz

```
## Troubleshooting

# Ports already in use

```bash 

# Change ports in docker-compose.yml
ports:
  - "8001:8000"  # Use different port
  - "8081:8080"

```

# Ports already in use

```bash

# Change ports in docker-compose.yml
ports:
  - "8001:8000"  # Use different port
  - "8081:8080"

```

# Cannot connect to API

``` bash
# Check if containers are running
docker ps

# View logs
docker-compose logs netpulse

# Restart
docker-compose restart

```

# Database issues

```bash
# Recreate database
docker-compose down
rm -rf data/
docker-compose up -d
```
# Uninstall
``` bash 
# Stop and remove containers
docker-compose down

# Remove data (optional)
rm -rf data/

# Remove images
docker rmi netpulse_netpulse

```
## Support

* GitHub Issues: https://github.com/Kmmadu/NetPulse/issues
* Documentation: https://github.com/Kmmadu/NetPulse

## One-Command Setup for Users

# Share this with your users:

```bash 
git clone https://github.com/Kmmadu/NetPulse.git && cd NetPulse && cp network-monitor/.env.example network-monitor/.env && nano network-monitor/.env && docker-compose up -d
```

That's it! NetPulse is running. 🚀