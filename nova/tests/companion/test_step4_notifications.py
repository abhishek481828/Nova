"""Unit tests for Step 4: Notification Listener & Event Interception."""

import pytest
import asyncio
from nova.companion.plugins.notification_plugin import NotificationPlugin
from nova.companion.events.event_bus import EventBus
from nova.companion.protocol.schemas import EventMessage
from nova.companion.manager import CompanionManager


def test_notification_plugin_registration():
    mgr = CompanionManager()
    plugin = mgr.plugin_registry.get_plugin_for_action("notification.list_active")
    assert plugin is not None
    assert plugin.plugin_name == "system.notifications"


@pytest.mark.asyncio
async def test_notification_event_bus_interception():
    mgr = CompanionManager()
    plugin = mgr.notification_plugin

    # 1. Simulate WhatsApp Notification Event
    wa_event = EventMessage(
        source="phone-a13",
        event="whatsapp.received",
        payload={
            "package_name": "com.whatsapp",
            "title": "Alice",
            "text": "Hey Nova, did you finish Step 4?"
        }
    )
    await mgr.event_bus.publish(wa_event)
    assert len(plugin.whatsapp_messages) == 1
    assert plugin.whatsapp_messages[0]["title"] == "Alice"

    # 2. Simulate OTP Code Event
    otp_event = EventMessage(
        source="phone-a13",
        event="otp.detected",
        payload={
            "otp_code": "849201",
            "source_app": "com.google.android.apps.messaging",
            "raw_message": "Your verification code is 849201. Valid for 5 min."
        }
    )
    await mgr.event_bus.publish(otp_event)
    assert len(plugin.intercepted_otps) == 1
    assert plugin.intercepted_otps[0]["otp_code"] == "849201"

    # 3. Simulate Missed Call Event
    call_event = EventMessage(
        source="phone-a13",
        event="call.missed",
        payload={
            "package_name": "com.google.android.dialer",
            "title": "Missed Call",
            "text": "Missed call from +1-555-0199"
        }
    )
    await mgr.event_bus.publish(call_event)
    assert len(plugin.missed_calls) == 1
    assert plugin.missed_calls[0]["text"] == "Missed call from +1-555-0199"
