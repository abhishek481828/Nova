# Nova v2.0 — System Architecture

Nova v2.0 is a distributed, offline-first AI ecosystem composed of Nova Core (Linux host) and the Nova Companion App (Android device).

---

## 1. High-Level Subsystem Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                Nova Core                                │
│                                                                         │
│   ┌───────────────────┐  ┌───────────────────┐  ┌────────────────────┐   │
│   │   Intent Engine   │  │  Speech-to-Text   │  │ Command Dispatcher │   │
│   │  (Ollama / Local) │  │ (Whisper / Local) │  │  (40+ Action Modules) │
│   └─────────┬─────────┘  └─────────┬─────────┘  └─────────┬──────────┘   │
│             │                      │                      │              │
│             └──────────────────────┼──────────────────────┘              │
│                                    ▼                                     │
│                     Companion Gateway & Device Manager                   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (WebSocket / AES-256)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                             Android Companion                           │
│                                                                         │
│   ┌───────────────────┐  ┌───────────────────┐  ┌────────────────────┐   │
│   │ Device Management │  │ Accessibility     │  │ Audio Streamer     │   │
│   │ & File Handler    │  │ Service           │  │ (PCM / TTS)        │   │
│   └───────────────────┘  └───────────────────┘  └────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase Architecture Roadmap

- **Phase A**: Companion Gateway & Pairing Foundation
- **Phase B**: Device Discovery & Dynamic Capability Registry
- **Phase C**: Hardware Abstraction & Telemetry Engine
- **Phase D**: Communication Subsystem (SMS, Calls, Contacts, OTP)
- **Phase E**: Camera & Media Pipeline Subsystem
- **Phase F**: Accessibility & Application Automation
- **Phase G**: Screen Capture & Remote Interaction Subsystem
- **Phase H**: Audio Streaming & Voice Integration Subsystem
- **Phase I**: Device Management & Remote Operations Subsystem
- **Phase J**: Production Hardening, Release & Final Validation
