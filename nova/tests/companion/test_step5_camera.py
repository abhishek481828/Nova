"""Unit tests for Step 5: Camera Plugin & Media Upload."""

import pytest
import asyncio
import os
import base64
from nova.companion.plugins.camera_plugin import CameraPlugin
from nova.companion.plugins.plugin_registry import PluginRegistry
from nova.companion.gateway.rest_api import upload_media, MediaUploadRequest


def test_camera_plugin_registration():
    registry = PluginRegistry()
    plugin = CameraPlugin()
    registry.register_plugin(plugin)

    assert registry.get_plugin_for_action("camera.capture_photo") == plugin
    assert registry.get_plugin_for_action("camera.record_video") == plugin
    assert registry.get_plugin_for_action("camera.scan_qr") == plugin
    assert registry.get_plugin_for_action("camera.ocr_scan") == plugin


@pytest.mark.asyncio
async def test_camera_plugin_execution():
    plugin = CameraPlugin()
    res = await plugin.execute(
        device_id="phone-a13",
        action="camera.capture_photo",
        payload={"camera_selector": "front", "quality": 95}
    )
    assert res["action"] == "camera.capture_photo"
    assert res["camera_facing"] == "front"
    assert res["quality"] == 95


@pytest.mark.asyncio
async def test_media_upload_endpoint():
    raw_content = b"Simulated JPEG Image Content from Samsung Galaxy A13"
    b64_content = base64.b64encode(raw_content).decode('utf-8')

    req = MediaUploadRequest(
        device_id="phone-a13",
        file_name="test_capture.jpg",
        file_type="image/jpeg",
        file_base64=b64_content
    )

    res = await upload_media(req)
    assert res.status == "uploaded"
    assert res.size_bytes == len(raw_content)
    assert os.path.exists(res.file_path)

    # Cleanup test media file
    if os.path.exists(res.file_path):
        os.remove(res.file_path)
