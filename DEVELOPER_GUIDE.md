# Nova v2.0 — Developer & Contribution Guide

This guide describes how to extend, build, and test Nova v2.0.

---

## 1. Directory Structure

- `nova/actions/`: Python action handlers (`BaseAction` implementations).
- `nova/companion/`: Gateway server, WebSocket protocols, security managers, and dashboard.
- `android/`: Native Android Kotlin Companion app (`com.nova.companion`).
- `nova/tests/companion/`: Pytest unit and integration test suites.

---

## 2. Adding a New Action Class

1. Inherit from `BaseAction` in `nova/actions/`:
   ```python
   from nova.actions.base import BaseAction

   class CustomAction(BaseAction):
       @property
       def action_name(self) -> str:
           return "custom_action"

       def execute(self, params: dict) -> str:
           return "Custom action executed."
   ```

2. Register `custom_action` in `VALID_ACTIONS` in `nova/parser.py`.
3. Add a unit test in `nova/tests/companion/`.

---

## 3. Running Pytest Suite

Run all tests:
```bash
PYTHONPATH=. .venv/bin/pytest nova/tests/companion/ -v
```
