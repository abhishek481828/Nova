"""Unit tests for DeviceManager, EventBus & Plugins."""

import pytest
import asyncio
from nova.companion.devices.device_manager import DeviceManager
from nova.companion.devices.health_monitor import HealthMonitor
from nova.companion.events.event_bus import EventBus
from nova.companion.protocol.schemas import EventMessage, HeartbeatMessage
from nova.companion.plugins.plugin_registry import PluginRegistry
from nova.companion.plugins.hardware_plugins import FlashlightPlugin
from nova.companion.storage.db import CompanionDatabase


def test_device_manager_and_health(tmp_path):
    db_path = str(tmp_path / "test_companion.db")
    db = CompanionDatabase(db_path=db_path)
    dm = DeviceManager(db=db)
    hm = HealthMonitor(dm)

    dev = dm.register_or_update_device(
        device_id="dev-test-1",
        name="Pixel 8",
        platform="android",
        capabilities=["flashlight", "battery"]
    )
    assert dev.name == "Pixel 8"
    assert dm.is_online("dev-test-1") is True

    hb = HeartbeatMessage(device_id="dev-test-1", battery_level=90, is_charging=True)
    dm.record_heartbeat(hb)

    report = hm.check_health()
    assert report["dev-test-1"]["status"] == "HEALTHY"
    assert report["dev-test-1"]["battery_level"] == 90


@pytest.mark.asyncio
async def test_event_bus_pub_sub():
    bus = EventBus()
    received_events = []

    async def on_battery_changed(evt: EventMessage):
        received_events.append(evt)

    bus.subscribe("battery.changed", on_battery_changed)

    evt = EventMessage(source="phone-1", event="battery.changed", payload={"level": 15})
    await bus.publish(evt)

    assert len(received_events) == 1
    assert received_events[0].payload["level"] == 15


def test_plugin_registry():
    registry = PluginRegistry()
    plugin = FlashlightPlugin()
    registry.register_plugin(plugin)

    assert registry.get_plugin_for_action("flashlight.on") == plugin
    assert "hardware.flashlight" in registry.list_plugins()
