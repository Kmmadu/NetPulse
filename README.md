![NetPulse Dashboard](https://raw.githubusercontent.com/Kmmadu/NetPulse/main/network-monitor/web/dashboard.png)

# NetPulse - Network Monitoring System

> Monitor your network and get instant email alerts when devices go down and recover.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-blue.svg)](https://fastapi.tiangolo.com)

**NetPulse** is a lightweight, self-hosted network monitoring system that alerts you via email when devices go down and when they come back up. It is designed for network engineers, ISPs, and IT teams who need a simple and reliable monitoring solution without heavy infrastructure.

---

## Features

| Feature | Description |
|--------|------------|
| Real-time Monitoring | Ping devices at configurable intervals |
| Email Alerts | Instant notifications for DOWN and RECOVERY events |
| Downtime Tracking | Calculates how long outages last |
| Recovery Detection | Alerts when devices come back online |
| Web Dashboard | View device status in a browser |
| Smart Cooldown | Prevents alert spam |
| Flapping Detection | Detects unstable devices |

---

## How It Works

1. Add devices (name + IP address)
2. NetPulse continuously monitors them using ICMP (ping)
3. Alerts are triggered only on meaningful state changes

**Flow:**
Device goes DOWN → Alert sent → Device recovers → Recovery alert with downtime

---

## Quick Start

### One-Command Install (Recommended)

```bash
git clone https://github.com/Kmmadu/NetPulse.git
cd NetPulse
chmod +x install.sh
./install.sh
```

---
## Manual Installation

```
# Clone repository
git clone https://github.com/Kmmadu/NetPulse.git
cd NetPulse

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r network-monitor/requirements.txt

# Setup environment variables
cp .env.example .env
nano .env

# Start API
python api_run.py

# Start frontend
cd web
python3 -m http.server 8080
```
---

## Configuration

### Edit `.env`

```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-email@gmail.com
SMTP_TO=alerts@yourdomain.com

ALERTS_ENABLED=true
ALERT_DOWN_COOLDOWN=5
ALERT_RECOVERY_COOLDOWN=5
ALERT_ERRATIC_COOLDOWN=30
PREMIUM_MODE=false
```
---

## Gmail Setup (App Password)

1. Enable 2-Factor Authentication
2. Visit: https://myaccount.google.com/apppasswords
3. Generate an App Password
4. Use it as SMTP_PASSWORD

---

## Service Management (Systemd)

```
# Check status
sudo systemctl status netpulse-api netpulse-monitor

# View logs
sudo journalctl -u netpulse-api -f

# Restart
sudo systemctl restart netpulse-api netpulse-monitor

# Stop
sudo systemctl stop netpulse-api netpulse-monitor

```
---

## Backup & Restore

```
# Manual backup
./scripts/backup.sh

# Backups stored in:
./backups/

# Automatic backup runs daily (cron)

```
---

## Email Alert Examples

### Device Down

Subject: [NetPulse] Device Down – Core Router

Device: Core Router
IP Address: 10.0.0.1
Status: DOWN
Time: 10:32 PM

### Device Recovery

Subject: [NetPulse] Device Restored – Core Router

Device: Core Router
Status: ONLINE
Recovered At: 10:37 PM
Downtime: 5 minutes

---

## Project Structure

```
NetPulse/
├── network-monitor/
│ ├── app/ # Backend logic
│ ├── web/ # Frontend UI
│ ├── data/ # SQLite database
│ └── requirements.txt
├── scripts/
├── backups/
├── install.sh
└── README.md
```
---

## Troubleshooting

### API not starting

```
sudo fuser -k 8000/tcp
sudo systemctl restart netpulse-api
```

### No email alerts
```
python -c "from app.services.alert_v2 import AlertServiceV2; AlertServiceV2().send_test_alert()"
```

### Devices stuck in UNKNOWN

* Start monitoring from dashboard
* Wait for first check cycle

### Check database
```
sqlite3 data/monitor.db "SELECT * FROM devices;"

```
### Uninstall

```
./uninstall.sh

```
### Roadmap

* Availability reports (Premium)
* Historical graphs
* Slack/Teams notifications
* SMS alerts
* SNMP monitoring
* Multi-location monitoring

### Use Cases

* ISP device monitoring
* Network uptime tracking
* Internal infrastructure monitoring
* Lightweight alternative to PRTG/Zabbix

---

## License

MIT License

---

##  Author

Built by Mmadubugwu Kingsley Obinna — Network Engineer & Builder

---

## Support
* Issues: GitHub Issues
* Discussions: GitHub Discussions
