# Nova v2.0 — Production Installation Guide

This guide details environment setup and installation for Nova v2.0 on Linux and the Samsung Galaxy A13 Android Companion.

---

## 1. Prerequisites

- **Host Operating System**: Linux (NixOS, Ubuntu, Debian, Fedora, Arch)
- **Python**: 3.12+
- **JDK**: OpenJDK 17 (for Android Companion compilation)
- **Android Device**: Samsung Galaxy A13 (or Android 10+ smartphone) with USB Debugging enabled

---

## 2. Automated One-Command Installation

Run the automated installer:
```bash
./install.sh
```

---

## 3. Manual Installation

1. Create Python Virtual Environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install Core & Voice Dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-voice.txt
   ```

3. Initialize Logging Directories:
   ```bash
   mkdir -p logs backups
   ```

4. Launch Nova System:
   ```bash
   ./start.sh
   ```
