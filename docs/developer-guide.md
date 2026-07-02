# Developer Guide

This guide details code standards, patterns, and development workflow rules.

---

## Code Quality Standards
*   **Decoupling**: Keep system execution loops separated from action skills.
*   **Asynchronous Processing**: Non-blocking processes in voice state updates must leverage `async_log`.
*   **Error Handling**: Wrap device access and external REST requests with retry blocks.

---

## Adding New Actions
To define a new custom command skill:
1. Create a subclass of `BaseAction` inside `nova/actions/`.
2. Implement `@property def action_name(self)` and `def execute(self, params: Dict[str, Any])`.
3. Register the skill inside `nova/actions/__init__.py`.
