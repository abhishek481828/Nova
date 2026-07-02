# Architecture Guide

This document describes the high-level cognitive architecture of the Nova assistant.

---

## Subsystem Design

```mermaid
graph TD
    A["Voice Input (Mic)"] --> B["DSP Filters (HPF/AGC/VAD)"]
    B --> C["Wake Detection (OpenWakeWord)"]
    C --> D["Speaker Verification (Resemblyzer)"]
    D --> E["Whisper STT"]
    E --> F["Cognitive Core & AI Planner"]
    F --> G["Browser Automation"]
    F --> H["REST Services"]
    F --> I["Dynamic Plugins"]
    F --> J["Telemetry Dashboard (WebSockets)"]
```

### Subsystems Breakdown:
1.  **Voice Subsystem**: Handles capture and verification of the user's speech.
2.  **Browser Subsystem**: Operates Playwright Chromium processes headed/headless.
3.  **AI Planning Subsystem**: Breaks down goals into structured steps.
4.  **Dashboard Subsystem**: Telemetry event publishing.
