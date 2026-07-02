# Dashboard Guide

This document describes the telemetry dashboard system.

---

## Architecture
*   **Websockets Server**: Binds to port `11436` and broadcasts voice states and executor alerts.
*   **Event Bus**: Core components emit telemetry entries via `nova.dashboard.event_bus.emit()`.
*   **Frontend UI**: React-based dashboard displaying system health charts, latency, and log details.
