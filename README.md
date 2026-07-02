# 🧠 Nova AI Desktop Assistant

Nova is a highly modular, next-generation cognitive desktop assistant built with local and cloud-based AI capabilities. Featuring an advanced real-time voice pipeline with speaker verification, resilient browser automation, a modular plan reasoning engine, and a live web telemetry dashboard, Nova acts as a powerful orchestrator for your local workflows.

---

## 📸 Screenshots & Demos

### Telemetry Dashboard
![Dashboard Screenshot Placeholder](docs/images/dashboard_screenshot.png)

### Voice Pipeline Flow
![Voice Flow Screenshot Placeholder](docs/images/voice_flow.png)

### Video Demonstration
[Watch Nova in Action (Demo Video Placeholder)](https://youtube.com/demo-placeholder)

---

## ✨ Features

*   **🎙️ Real-time Voice Loop**: Low-latency stream handling with built-in voice activity detection (VAD), high-pass filtering, and automatic gain control.
*   **🧑 Speaker Verification**: Integrated speaker verification via Resemblyzer to ensure only authorized voices trigger actions.
*   **🌐 Resilient Browser Automation**: Playwright-based browser execution that automatically handles tab recovery, element interactions, and credentials.
*   **🧩 Cognitive Planning & Reasoning**: Modular task breakdown planner that translates queries into structured steps instead of unsafe shell strings.
*   **📊 Telemetry Dashboard**: Live monitoring web page showing device health, status reports, and execution events via WebSockets.
*   **🔌 Extensible Plugin System**: Dynamic action loader for custom skill integrations.
*   **🛡️ Robust Error Recovery**: Automated recovery drivers for device drops and network timeouts.

---

## 🛠️ Requirements

*   **Operating System**: Linux (NixOS highly recommended and supported out of the box via `shell.nix`).
*   **Python**: Version `3.12` or higher.
*   **System Libraries**: `ffmpeg`, `libstdc++.so.6` (handled automatically inside the `nix-shell`).

---

## 🚀 Quick Start

### NixOS (Recommended)
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/Nova.git
   cd Nova
   ```
2. Drop into the pre-configured nix shell:
   ```bash
   nix-shell
   ```
3. Initialize the environment:
   ```bash
   cp .env.example .env
   # Edit .env and supply your API keys (Ollama, Gemini, ElevenLabs, etc.)
   ```
4. Start the interactive assistant:
   ```bash
   nova --text
   ```

### Non-Nix Linux Systems
1. Ensure dependencies like `ffmpeg` are installed via your package manager.
2. Initialize virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt -r requirements-voice.txt
   ```
3. Copy and configure env file:
   ```bash
   cp .env.example .env
   ```
4. Run:
   ```bash
   python -m nova.main --text
   ```

---

## 🎙️ Subsystem Setup

### Voice Setup & Enrollment
To train the speaker verification model to recognize your specific voice:
```bash
nova voice-setup
```
To reset your voice profile:
```bash
nova voice-reset
```
To run the automated voice subsystem self-test:
```bash
nova voice-test
```

### Browser Automation Setup
To run browser tasks, play music, or scrape content, configure Chromium using playbooks:
```bash
# Add browser paths/credentials to your config or .env file
```

---

## 🧠 Architecture Overview

Nova uses a decoupled cognitive architecture to handle audio streams, planners, and dashboard reporting:

```
  🎤 Microphone ──► DSP (Filters/AGC) ──► VAD ──► OpenWakeWord
                                                        │
  🧠 Nova core  ◄── LLM Planner  ◄── Whisper STT ◄── Speaker Verification
```

### Folder Structure
```
├── docs/                 # Subsystem user/developer guides
├── nova/                 # Main application source code
│   ├── actions/          # Executable skill action adapters
│   ├── ai/               # Intent parsing and LLM planners
│   │   └── planner/      # Goal decomposition and templates
│   ├── browser/          # Chromium controller & site playbooks
│   ├── core/             # CLI, TCP clients, and daemon launcher
│   ├── dashboard/        # Websocket backend and React frontend
│   ├── services/         # REST client adapters (Weather, News, etc.)
│   └── voice/            # Audio processors and wake word detection
├── tests/                # Automated pytest unit tests
└── shell.nix             # NixOS system dependencies environment shell
```

---

## 🧪 Testing

Run the full automated test suite containing 304 unit and stress tests:
```bash
nix-shell --run ".venv/bin/python -m pytest"
```

---

## 🗺️ Project Status & Roadmap

Nova is currently at status **v1.0.0 Stable Release**.

### Upcoming Releases:
*   **v1.1.0**: Memory optimization, SQLite-based RAG support.
*   **v1.2.0**: Multimodal vision integrations.
*   **v2.0.0**: Distributed local agent swarm control.

---

## 🤝 Contributing

Contributions are welcome! Please review [CONTRIBUTING.md](CONTRIBUTING.md) and our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## 📄 License

Distributed under the Apache 2.0 License. See [LICENSE](LICENSE) for more information.

---

## ✉️ Contact

*   **Project Lead**: Abhishek (abhishek@domain.example)
*   **GitHub Issues**: [https://github.com/your-username/Nova/issues](https://github.com/your-username/Nova/issues)
