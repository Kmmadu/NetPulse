# 🌐 NetPulse

**NetPulse** is a lightweight, local network monitoring system designed for ISP and enterprise environments. It continuously monitors network devices using ICMP (ping), detects downtime, logs events, and provides a foundation for a web-based dashboard.

---

## 🚀 Features

* 📡 Multi-device monitoring (private & public IPs)
* 🔁 Retry logic to prevent false alerts
* 🟢🔴 Real-time UP/DOWN status detection
* 📝 Structured logging with timestamps and latency
* ⚡ Continuous monitoring engine
* 🧱 Modular architecture (ready for scaling)
* 🌐 Future-ready for web dashboard integration

---

## 🧠 How It Works

NetPulse operates using a polling mechanism:

1. Devices are defined with IP, name, and retry settings
2. The monitoring engine sends periodic ping requests
3. Responses are analysed to determine device status
4. Failures are tracked using retry logic
5. Status changes (UP ↔ DOWN) are detected and logged

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
