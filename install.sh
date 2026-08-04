#!/usr/bin/env bash
# ==============================================================================
# Nova v2.0 Production Installation Script
# Target: Linux / NixOS Environment
# ==============================================================================

set -e

echo "🚀 Installing Nova v2.0 Core Environment..."

# Create Python virtual environment if not present
if [ ! -d ".venv" ]; then
    echo "📦 Creating Python 3.12 virtual environment..."
    python3 -m venv .venv
fi

echo "📦 Installing Core Python Dependencies..."
.venv/bin/pip install --upgrade pip setuptools wheel
if [ -f "requirements.txt" ]; then
    .venv/bin/pip install -r requirements.txt
fi

if [ -f "requirements-voice.txt" ]; then
    echo "🎙️ Installing Voice & Audio Streaming Dependencies..."
    .venv/bin/pip install -r requirements-voice.txt || echo "Warning: Optional voice dependencies skipped."
fi

# Ensure log directory exists
mkdir -p logs

echo "✅ Nova v2.0 Environment Installation Complete!"
