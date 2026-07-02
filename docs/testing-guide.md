# Testing Guide

This guide details how to run unit and stress tests.

---

## Running the Suite

### NixOS (Standard)
```bash
nix-shell --run ".venv/bin/python -m pytest"
```

### Standard Environments
Activate virtual environment and execute pytest:
```bash
source .venv/bin/activate
python -m pytest
```
---

## Coverage
The 304 unit tests cover planning parsing, memory stress tests, local VAD fallbacks, and circular audio buffer operations.
