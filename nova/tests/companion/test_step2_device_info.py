"""Unit tests for Step 2: Device Information Plugin & Telemetry."""

import pytest
import asyncio
from nova.companion.plugins.device_info import DeviceInfoPlugin
from nova.companion.plugins.plugin_registry import PluginRegistry
from nova.companion.devices.device_manager import DeviceManager
from nova.companion.storage.db import CompanionDatabase
from nova.companion.protocol.schemas import HeartbeatMessage, EventMessage


def test_device_info_plugin_registration():
    registry = PluginRegistry()
    plugin = DeviceInfoPlugin()
    registry.register_plugin(plugin)

    assert registry.get_plugin_for_action("device.get_info") == plugin
    assert registry.get_plugin_for_action("device.get_telemetry") == plugin
    assert registry.get_plugin_for_action("wifi.get_info") == plugin
    assert "hardware.device_info" in registry.list_plugins()


def test_device_telemetry_aggregation(tmp_path):
    db_path = str(tmp_path / "test_step2_device_info.db")
    db = CompanionDatabase(db_path=db_path)
    dm = DeviceManager(db=db)

    # Register device Specs
    device_rec = dm.register_or_update_device(
        device_id="galaxy-a13-001",
        name="Samsung Galaxy A13",
        platform="android",
        capabilities=["device.get_info", "device.get_telemetry", "wifi.get_info"],
        protocol_version="2.0"
    )

    # Update record with full device specs in metadata
    specs = {
        "manufacturer": "Samsung",
        "model": "SM-A135F",
        "brand": "samsung",
        "android_version": "12",
        "sdk_int": 31,
        "battery": {"level": 85, "is_charging": True},
        "ram": {"total_gb": "4.00 GB", "available_gb": "1.80 GB"},
        "storage": {"total_gb": "64.00 GB", "available_gb": "28.50 GB"},
        "wifi": {"is_connected": True, "ssid": "HomeNetwork_5G", "rssi": -55}
    }
    device_rec.metadata = specs
    dm.db.save_device(device_rec)

    retrieved = dm.db.get_device("galaxy-a13-001")
    assert retrieved is not None
    assert retrieved.name == "Samsung Galaxy A13"
    assert retrieved.metadata["manufacturer"] == "Samsung"
    assert retrieved.metadata["model"] == "SM-A135F"
    assert retrieved.metadata["ram"]["total_gb"] == "4.00 GB"
    assert retrieved.metadata["storage"]["available_gb"] == "28.50 GB"
    assert retrieved.metadata["wifi"]["ssid"] == "HomeNetwork_5G"


@pytest.mark.asyncio
async def test_device_info_plugin_execution():
    plugin = DeviceInfoPlugin()
    res = await plugin.execute(
        device_id="galaxy-a13-001",
        action="device.get_info",
        payload={}
    )
    assert res["action"] == "device.get_info"
    assert res["device_id"] == "galaxy-a13-001"
    assert res["status"] == "query_dispatched"
