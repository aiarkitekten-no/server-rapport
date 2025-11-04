# Plesk Health Check 🩺

Comprehensive health monitoring system for Plesk servers. This tool performs deep diagnostics across system, security, backups, email, and more - then generates beautiful reports showing only what needs attention.

## ✨ Features

### 🔍 Comprehensive Checks

- **System Health (A)**: uptime, load, CPU temp, RAM, swap, disk, I/O, SMART, RAID, kernel, dmesg
- **Packages (B)**: apt updates, unattended-upgrades, dpkg status
- **Network (C)**: interface errors, NTP sync
- **Security (D)**: world-writable files, RBL blacklist, UID 0 users, sensitive files
- **Plesk (E)**: license, logs, scheduler, backups, extensions, panel.ini, web pipeline, mail stack
- **Web Apps (F)**: TLS expiry, HSTS, HTTP 5xx errors, 404 floods
- **Database (G)**: MariaDB connections and health
- **Cron (H)**: scheduled task status, logrotate
- **Email (I)**: SPF/DKIM/DMARC, SMTP errors, queue size
- **ClamAV (J)**: daemon status, virus definition age
- **Backups (K)**: recent backups, external mounts
- **Logs (L)**: error patterns, repeated issues
- **TLS (O)**: certificate expiry, weak ciphers
- **Processes (N)**: zombies, CPU/memory hogs

### 📊 Smart Reporting

- **Terminal Report**: Color-coded console output (green/yellow/red)
- **HTML Email**: Beautiful email reports with charts and top 5 actions
- **Baseline Tracking**: Compare against previous runs to spot trends
- **Severity Scoring**: 0-100 scale with intelligent thresholds
- **Issues Only**: Reports show only problems, not everything

### 🛡️ Safe by Default

- **Read-Only Mode**: No changes made to your system
- **Timeouts**: All commands have timeouts
- **Error Handling**: Graceful degradation when tools unavailable

## 📦 Installation

```bash
# Clone or copy to your server
cd /opt
git clone <repo> plesk-health-check
cd plesk-health-check

# Install dependencies
pip3 install -r requirements.txt

# Make executable
chmod +x main.py
```

## 🚀 Usage

### Basic Usage

```bash
# Run with defaults
./main.py

# Verbose output
./main.py --verbose

# Save results to JSON
./main.py --json-output /var/log/plesk-health.json

# Force email report
./main.py --email
```

### Advanced Usage

```bash
# Save current state as baseline
./main.py --save-baseline

# Custom config file
./main.py --config /etc/plesk-health/custom-config.json

# Skip terminal output, only email
./main.py --no-terminal --email

# Enable logging to file
./main.py --log-file /var/log/plesk-health.log
```

### Automated Checks

Add to crontab for daily checks:

```bash
# Run daily at 6 AM
0 6 * * * /opt/plesk-health-check/main.py --email --no-terminal --log-file /var/log/plesk-health.log
```

## ⚙️ Configuration

Edit `config.json` to customize:

```json
{
  "general": {
    "read_only": true,
    "email_recipient": "terje@smartesider.no",
    "smtp_host": "localhost"
  },
  "thresholds": {
    "disk_usage_critical": 90,
    "memory_usage_warning": 85,
    "tls_expiry_warning_days": 30
  },
  "checks": {
    "enabled": {
      "system_health": true,
      "plesk": true,
      "security": true
    }
  }
}
```

## 📈 Understanding Results

### Severity Levels

- **✅ OK (0-30)**: Everything normal
- **⚠️ WARNING (31-70)**: Needs attention soon
- **🔴 CRITICAL (71-100)**: Immediate action required

### Exit Codes

- `0`: All checks OK
- `1`: Warnings found
- `2`: Critical issues found

## 🧠 AI Learning System

The `AI-learned/` directory contains accumulated knowledge:

- **fungerer.json**: Proven working methods
- **feil.json**: Known failures to avoid
- **usikkert.json**: Untested approaches
- **godekilder.json**: Useful resources
- **metoder.json**: Standard patterns

These files help improve the tool over time.

## 📁 Directory Structure

```
plesk-health-check/
├── main.py                 # Main entry point
├── config.json             # Configuration
├── requirements.txt        # Python dependencies
├── checks/                 # Health check modules
│   ├── system_health.py
│   ├── plesk.py
│   ├── security.py
│   └── ...
├── utils/                  # Utility functions
│   ├── common.py
│   ├── severity.py
│   ├── base_checker.py
│   └── baseline.py
├── reports/                # Report generators
│   ├── terminal_report.py
│   └── email_report.py
├── data/                   # Data storage
│   └── baselines/          # Historical baselines
└── AI-learned/             # Knowledge base
    ├── fungerer.json
    ├── feil.json
    └── ...
```

## 🔧 Requirements

- Python 3.8+
- Root or sudo access (for some checks)
- Optional: smartmontools, iostat, ClamAV

## 🤝 Contributing

This tool is designed to be extensible. To add new checks:

1. Create new checker in `checks/` inheriting from `BaseChecker`
2. Implement `run()` method returning list of `CheckResult`
3. Add to `main.py` initialization
4. Update config.json with new check option

## 📝 License

MIT License - See LICENSE file

## 👤 Author

Created for Terje by AI Assistant
Date: 2025-11-04

## 🆘 Support

For issues or questions:
- Check AI-learned/ for known solutions
- Review logs with `--verbose --log-file`
- Verify configuration in config.json

---

**Note**: This tool is read-only by default and safe to run. It won't make any changes to your system unless explicitly configured otherwise.
