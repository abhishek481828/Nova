# Nova AI Desktop Assistant

Nova is an advanced, voice- and text-activated AI Desktop Assistant designed for NixOS. It features automated browser command execution (CDP remote debugging), system integration (volume, brightness, power control), custom package management (Nix), and a real-time web-based Mission Control Dashboard.

---

## 🚀 How to Start the Project

You can run Nova in **Interactive CLI mode** or as a **Background Daemon** with the web dashboard.

### 1. Start the Background Daemon & Dashboard (Recommended)
To run Nova in the background and start the web dashboard, use the launcher script:
```bash
nova start
```
*Alternatively, you can start the systemd user service directly:*
```bash
systemctl --user start nova.service
```

Once started:
* **Nova Mission Control Dashboard**: Open **[http://127.0.0.1:11436](http://127.0.0.1:11436)** in your browser to view system telemetry, events log, active voice state, and the Dialogue Stream panel.
* The daemon listens for TCP input triggers on port `11435`.

### 2. Run Interactive CLI Mode
To start Nova in your terminal interactively:
* **Voice Mode (Default)**:
  ```bash
  nova
  ```
* **Text Mode (REPL)**:
  ```bash
  nova --text
  ```

---

## 🛠️ Command Launcher Usage (`nova`)

The custom launcher script `nova` supports several commands:

| Command | Action |
|---|---|
| `nova start` | Starts the background daemon service |
| `nova stop` | Stops the background daemon service |
| `nova restart` | Restarts the background daemon service |
| `nova status` | Prints the status of all daemon modules |
| `nova` | Launches interactive voice loops |
| `nova --text` | Launches interactive text REPL |
| `nova <query>` | Sends a single command to the running daemon |
| `nova voice-test` | Runs audio and speaker verification diagnostics |
| `nova voice-setup` | Enrolls/re-enrolls your voice speaker profile |
| `nova voice-reset` | Resets/deletes the speaker profile |

---

## 📦 Project Setup & Installation

If you are setting up the project on a new system or environment, follow these steps:

### Prerequisites
* NixOS with `nix-shell`
* Python 3.12+ (loaded via `shell.nix`)

### Setup Environment
1. Enter the Nix development shell:
   ```bash
   nix-shell shell.nix
   ```
2. Initialize and activate the virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements-voice.txt
   ```
4. Copy the environment template and set up your API keys (e.g. Ollama, Tavily, etc.):
   ```bash
   cp .env.example .env
   ```
5. Build the Dashboard Frontend:
   Navigate to the frontend folder, install dependencies, and compile the UI static files:
   ```bash
   cd nova/dashboard/frontend
   npm install
   npm run build
   cd ../../..
   ```

---

## ⚙️ Configuration (.env)

Nova is configured using the `.env` file at the root of the project directory. Make sure to define:
* `NEBIUS_API_KEY`: API key for LLM intent parsing
* `TAVILY_API_KEY`: For web searching
* `OLLAMA_API_URL`: Ollama local endpoint (defaults to `http://localhost:11434`)
* `CHROMIUM_DEVTOOLS_PORT`: CDP remote debugging port (defaults to `9222`)
