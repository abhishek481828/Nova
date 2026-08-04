#!/usr/bin/env bash
# ==============================================================================
# Nova v2.0 Configuration & Data Backup Script
# ==============================================================================

set -e

BACKUP_DIR="backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE_NAME="${BACKUP_DIR}/nova_v2_backup_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "📦 Creating Nova v2.0 Backup Archive: ${ARCHIVE_NAME}..."

tar -czf "$ARCHIVE_NAME" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.venv' \
    --exclude='android/.gradle' \
    --exclude='android/app/build' \
    logs/ \
    config/ 2>/dev/null || tar -czf "$ARCHIVE_NAME" logs/ 2>/dev/null

echo "✅ Backup created successfully: ${ARCHIVE_NAME}"
