#!/usr/bin/env bash
# ==============================================================================
# Nova v2.0 Restore Script
# ==============================================================================

set -e

ARCHIVE_PATH="$1"

if [ -z "$ARCHIVE_PATH" ]; then
    echo "Usage: ./restore.sh <path_to_tar_gz_archive>"
    exit 1
fi

if [ ! -f "$ARCHIVE_PATH" ]; then
    echo "Error: Archive file '$ARCHIVE_PATH' not found."
    exit 1
fi

echo "📦 Restoring Nova v2.0 from archive: ${ARCHIVE_PATH}..."

tar -xzf "$ARCHIVE_PATH"

echo "✅ Nova v2.0 System Restored Successfully!"
