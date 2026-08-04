#!/usr/bin/env bash
# ==============================================================================
# Nova v2.0 Release Packaging Script
# ==============================================================================

set -e

VERSION="2.0.0"
DIST_DIR="dist/nova-v${VERSION}"

echo "📦 Packaging Nova v${VERSION} Release Candidate..."

mkdir -p "$DIST_DIR"

# Copy core files
cp -r nova/ "$DIST_DIR/"
cp -r docs/ "$DIST_DIR/" 2>/dev/null || true
cp README.md INSTALLATION.md ANDROID_SETUP.md API_REFERENCE.md ARCHITECTURE.md DEVELOPER_GUIDE.md USER_GUIDE.md TROUBLESHOOTING.md SECURITY.md CHANGELOG.md RELEASE_NOTES.md "$DIST_DIR/" 2>/dev/null || true
cp install.sh start.sh update.sh backup.sh restore.sh "$DIST_DIR/"

# Copy Android APK if compiled
if [ -f "android/app/build/outputs/apk/debug/app-debug.apk" ]; then
    cp android/app/build/outputs/apk/debug/app-debug.apk "$DIST_DIR/nova-companion-v${VERSION}.apk"
fi

cd dist
zip -r "nova-v${VERSION}-release.zip" "nova-v${VERSION}" > /dev/null
cd ..

echo "✅ Nova v${VERSION} Release Package generated at: dist/nova-v${VERSION}-release.zip"
