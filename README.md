# NetPulse - Network Monitoring System

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

## 🏗️ Project Structure

```
network-monitor/
│
├── app/
│   ├── core/              # Monitoring engine
│   ├── services/          # Ping, alerts
│   ├── models/            # Data models
│   ├── database/          # SQLite setup
│   ├── api/               # Future API layer
│   └── utils/             # Helpers
│
├── cli/                   # CLI interface
├── config/                # Config files
├── data/                  # Database storage
├── tests/                 # Tests (future)
│
├── run.py                 # Entry point
└── requirements.txt
```

---

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/Kmmadu/netpulse.git
cd netpulse
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## ▶️ Usage

Run the monitoring system:

```bash
python run.py
```

From the CLI, you can:

* Add devices
* Remove devices
* Update device settings
* Start monitoring

---

## 📊 Example Output

```
🟢 [21:48:29] Service Providers (10.x.x.x) - UP (Latency: 7.3ms)
🔴 [21:48:31] Service Providers (10.x.x.x) - DOWN
```

---

## 🛠️ Roadmap

* [ ] SQLite database integration
* [ ] REST API (Flask/FastAPI)
* [ ] Web dashboard (React or HTML/JS)
* [ ] Email alert system
* [ ] SNMP monitoring
* [ ] Multi-network agent support

---

## 🎯 Use Case

NetPulse is ideal for:

* ISPs monitoring internal infrastructure
* Network engineers tracking link availability
* Small teams needing simple monitoring tools

---

## 🤝 Contributing

Contributions are welcome! Feel free to fork the repo and submit a pull request.

---

## 📄 License

MIT License

---

## 👨‍💻 Author

Built by Mmadubugwu Kingsley Obinna — Network Engineer & Builder 🚀
