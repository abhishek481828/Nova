# User Guide

This guide introduces how to interact with Nova using the Command Line Interface (CLI) and voice controls.

---

## 💻 CLI Commands

### Starting interactive modes
*   **REPL Text Mode**:
    ```bash
    nova --text
    ```
*   **Daemon Launcher Mode**:
    ```bash
    nova
    ```

### Direct Subsystem Control
*   `nova start`: Start the background assistant service.
*   `nova stop`: Stop the background assistant service.
*   `nova status`: View current daemon status.

---

## 🎙️ Voice Mode
Toggle voice mode inside the CLI or daemon. Speak the wake-word **"Hey Nova"** to activate listening. Nova will capture your command, verify your voice profile, execute the task, and speak back.
