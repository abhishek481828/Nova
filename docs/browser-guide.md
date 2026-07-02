# Browser Guide

This document describes the Playwright-based browser automation subsystem.

---

## Architecture
Nova wraps Playwright inside `nova/browser/manager.py` to coordinate browser processes.

---

## Resilience & Recovery
*   **Active Tab Polling**: Periodically queries open tabs. If Chromium crashes, the manager launches a recovery browser instance.
*   **Dynamic Selectors**: Element selectors use semantic identifiers. If a select query fails, search filters fallback to coordinates clicks.
