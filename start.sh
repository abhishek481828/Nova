#!/usr/bin/env bash
# ==============================================================================
# Nova v2.0 Production Process Launcher
# ==============================================================================

set -e

if [ "$1" == "--check" ]; then
    echo "Nova v2.0 Start Script OK"
    exit 0
fi

echo "🚀 Launching Nova v2.0 Production System..."

mkdir -p logs

# Start Gateway Server in background if not running
if ! pgrep -f "nova/companion/server.py" > /dev/null; then
    echo "🌐 Starting Nova Companion Gateway Server (Port 8000)..."
    PYTHONPATH=. .venv/bin/python nova/companion/server.py > logs/backend.log 2>&1 &
    sleep 1
fi

echo "✨ Starting Nova v2.0 Core REPL..."
PYTHONPATH=. .venv/bin/python -m nova.core.cli "$@"
