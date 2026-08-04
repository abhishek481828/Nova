"""Unit tests for Deployment Step 4: Device Information, Health Monitoring & Capability Registration."""

import pytest
import asyncio
import time
from nova.companion.devices.device_manager import DeviceManager
from nova.companion.events.event_bus import EventBus
from nova.companion.events.health_alerts import HealthAlertEvaluator
from nova.companion.storage.db import CompanionDatabase
from nova.companion.storage.models import DeviceRecord


def test_telemetry_db_persistence(tmp_path):
    db_file = str(tmp_path / "test_telemetry.db")
    db = CompanionDatabase(db_path=db_file)

    dev = DeviceRecord(
        device_id="phone-telemetry-01",
        name="Samsung Galaxy A13",
        platform="android",
        capabilities=["battery", "camera", "microphone"]
    )
    db.upsert_device(dev)

    telemetry_data = {
        "timestamp": time.time(),
        "battery_percent": 12,
        "is_charging": False,
        "battery_temp": 48.5,
        "ram_usage_percent": 92.4,
        "storage_usage_percent": 95.1,
        "wifi_signal_dbm": -72
    }
    db.record_telemetry("phone-telemetry-01", telemetry_data)

    latest = db.get_latest_telemetry("phone-telemetry-01")
    assert latest is not None
    assert latest["battery_percent"] == 12
    assert latest["battery_temp"] == 48.5


@pytest.mark.asyncio
async def test_health_alerts_triggering():
    event_bus = EventBus()
    alerts_triggered = []

    async def on_alert(event):
        alerts_triggered.append(event)

    event_bus.subscribe("health.alert.low_battery", on_alert)
    event_bus.subscribe("health.alert.high_temperature", on_alert)
    event_bus.subscribe("health.alert.storage_full", on_alert)
    event_bus.subscribe("health.alert.high_memory", on_alert)

    evaluator = HealthAlertEvaluator(event_bus)

    sample_telemetry = {
        "battery_percent": 10,
        "is_charging": False,
        "battery_temp": 49.0,
        "storage_usage_percent": 92.0,
        "ram_usage_percent": 94.0
    }

    alerts = await evaluator.evaluate_telemetry("phone-alert-01", sample_telemetry)
    assert len(alerts) == 4
    assert len(alerts_triggered) == 4


def test_dynamic_capability_registration(tmp_path):
    db_file = str(tmp_path / "test_caps.db")
    db = CompanionDatabase(db_path=db_file)
    dev_mgr = DeviceManager(db=db)

    # Register device with dynamically advertised capabilities
    adv_caps = ["battery", "flashlight", "clipboard", "camera.photo", "microphone.stream", "accessibility.click"]
    rec = dev_mgr.register_or_update_device(
        device_id="phone-caps-01",
        name="Samsung Galaxy A13 Dynamic",
        platform="android",
        capabilities=adv_caps
    )

    assert rec.capabilities == adv_caps
    retrieved = dev_mgr.get_device("phone-caps-01")
    assert retrieved is not None
    assert "accessibility.click" in retrieved.capabilities
