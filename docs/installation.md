# Installation Guide

This document describes how to install and initialize the Nova assistant.

---

## ❄️ NixOS Setup (Recommended)
1. Run `nix-shell` inside the root workspace to configure Python 3.12, dynamic linkers (`nix-ld`), and system audio libraries automatically:
   ```bash
   nix-shell
   ```
2. Copy and configure the environment file:
   ```bash
   cp .env.example .env
   # Add your API credentials inside .env
   ```

---

## 🐧 Standard Linux Setup
1. Verify system dependencies (`ffmpeg` and Python development headers).
2. Configure virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt -r requirements-voice.txt
   ```
3. Copy environment file:
   ```bash
   cp .env.example .env
   ```
