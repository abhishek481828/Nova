"""Database operations for Nova v2.0 Companion Subsystem."""

import sqlite3
import os
import time
import json
from typing import List, Optional, Dict, Any
from nova.companion.storage.models import DeviceRecord, SessionRecord


class CompanionDatabase:
    """Manages SQLite storage for Nova v2.0 companion devices, sessions, and telemetry history."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_path = os.path.expanduser("~/.nova/companion_v2.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # Device Records Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    protocol_version TEXT NOT NULL,
                    is_trusted INTEGER DEFAULT 1,
                    capabilities TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    metadata TEXT NOT NULL
                )
            """)

            # Sessions Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    is_revoked INTEGER DEFAULT 0,
                    FOREIGN KEY(device_id) REFERENCES devices(device_id)
                )
            """)

            # Telemetry History Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    battery_percent INTEGER,
                    is_charging INTEGER,
                    battery_temp REAL,
                    ram_usage_percent REAL,
                    storage_usage_percent REAL,
                    wifi_signal_dbm INTEGER,
                    raw_telemetry TEXT NOT NULL,
                    FOREIGN KEY(device_id) REFERENCES devices(device_id)
                )
            """)
            conn.commit()

    def save_device(self, device: DeviceRecord):
        self.upsert_device(device)

    def upsert_device(self, device: DeviceRecord):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO devices (device_id, name, platform, protocol_version, is_trusted, capabilities, created_at, last_seen, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    name=excluded.name,
                    platform=excluded.platform,
                    protocol_version=excluded.protocol_version,
                    is_trusted=excluded.is_trusted,
                    capabilities=excluded.capabilities,
                    last_seen=excluded.last_seen,
                    metadata=excluded.metadata
            """, (
                device.device_id,
                device.name,
                device.platform,
                device.protocol_version,
                1 if device.is_trusted else 0,
                json.dumps(device.capabilities),
                device.created_at,
                device.last_seen,
                json.dumps(device.metadata)
            ))
            conn.commit()

    def get_device(self, device_id: str) -> Optional[DeviceRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)).fetchone()
            if not row:
                return None
            return DeviceRecord(
                device_id=row["device_id"],
                name=row["name"],
                platform=row["platform"],
                protocol_version=row["protocol_version"],
                is_trusted=bool(row["is_trusted"]),
                capabilities=json.loads(row["capabilities"]),
                created_at=row["created_at"],
                last_seen=row["last_seen"],
                metadata=json.loads(row["metadata"])
            )

    def list_devices(self) -> List[DeviceRecord]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM devices").fetchall()
            return [
                DeviceRecord(
                    device_id=row["device_id"],
                    name=row["name"],
                    platform=row["platform"],
                    protocol_version=row["protocol_version"],
                    is_trusted=bool(row["is_trusted"]),
                    capabilities=json.loads(row["capabilities"]),
                    created_at=row["created_at"],
                    last_seen=row["last_seen"],
                    metadata=json.loads(row["metadata"])
                ) for row in rows
            ]

    def record_telemetry(self, device_id: str, telemetry: Dict[str, Any]):
        """Persists historical telemetry sample to database."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO telemetry_history (
                    device_id, timestamp, battery_percent, is_charging, battery_temp,
                    ram_usage_percent, storage_usage_percent, wifi_signal_dbm, raw_telemetry
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id,
                telemetry.get("timestamp", time.time()),
                telemetry.get("battery_percent", 85),
                1 if telemetry.get("is_charging") else 0,
                telemetry.get("battery_temp", 30.0),
                telemetry.get("ram_usage_percent", 45.0),
                telemetry.get("storage_usage_percent", 60.0),
                telemetry.get("wifi_signal_dbm", -65),
                json.dumps(telemetry)
            ))
            conn.commit()

    def get_latest_telemetry(self, device_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT raw_telemetry FROM telemetry_history
                WHERE device_id = ? ORDER BY timestamp DESC LIMIT 1
            """, (device_id,)).fetchone()
            if row:
                return json.loads(row["raw_telemetry"])
            return None
