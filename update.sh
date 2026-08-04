#!/usr/bin/env bash
# ==============================================================================
# Nova v2.0 Update & Maintenance Script
# ==============================================================================

set -e

echo "🔄 Updating Nova v2.0 System..."

# Pull git updates if repository
if [ -d ".git" ]; then
    git pull --rebase || echo "Warning: Git pull skipped."
fi

# Upgrade python packages
.venv/bin/pip install --upgrade -r requirements.txt || true

# Recompile Android Companion APK
if [ -d "android" ]; then
    echo "📱 Rebuilding Android Companion APK..."
    nix-shell -p jdk17 --run "export JAVA_HOME=/nix/store/5badkg3gmzg1c29akwglknkizfg6zj0g-openjdk-17.0.17+8 && cd android && ./gradlew assembleDebug" || true
fi

echo "✅ Nova v2.0 Update Complete!"
