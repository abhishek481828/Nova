# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-07-02

### Added
*   Dynamic framework template match rules via external configuration file `mappings.json`.
*   Systemd user service config file (`home.nix` configuration layout) to manage the daemon service.
*   Speaker profile reset and verification Wizards.

### Changed
*   Decoupled circular CLI dependencies by importing `get_greeting` directly from `orchestrator`.
*   Refactored `assistant.py` to delegate launcher, systemctl commands, and health checks to the new `orchestrator.py` module.
*   Refactored the voice pipeline loop coordinator in `core.py` to extract diagnostics (`diagnostics.py`), wake loop (`wake.py`), and working memory TURN synchronization (`memory.py`).

### Fixed
*   Resolved NameErrors in `processors.py` due to missing `voice_config`, `threading`, `collections`, and `json` imports.
*   Resolved `sounddevice as sd` NameError in voice pipeline core initialization.
*   Resolved `public_ip` UnboundLocalError in `rich_system_info.py` by initializing the variable.
