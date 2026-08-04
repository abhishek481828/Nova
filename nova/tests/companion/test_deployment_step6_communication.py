"""Unit tests for Deployment Step 6: Notification & Communication System."""

import pytest
import asyncio
from nova.companion.plugins.notification_plugin import NotificationPlugin
from nova.companion.plugins.system_plugins import SMSPlugin
from nova.companion.plugins.communication_plugins import CallPlugin, ContactsPlugin
from nova.companion.plugins.plugin_registry import PluginRegistry


def test_communication_plugin_registration():
    registry = PluginRegistry()
    notif = NotificationPlugin()
    sms = SMSPlugin()
    call = CallPlugin()
    contacts = ContactsPlugin()

    registry.register_plugin(notif)
    registry.register_plugin(sms)
    registry.register_plugin(call)
    registry.register_plugin(contacts)

    # Notifications
    assert registry.get_plugin_for_action("notification.list_active") == notif

    # SMS
    assert registry.get_plugin_for_action("sms.read") == sms
    assert registry.get_plugin_for_action("sms.send") == sms

    # Calls
    assert registry.get_plugin_for_action("call.make") == call
    assert registry.get_plugin_for_action("call.history") == call
    assert registry.get_plugin_for_action("call.missed") == call

    # Contacts
    assert registry.get_plugin_for_action("contacts.search") == contacts
    assert registry.get_plugin_for_action("contacts.list") == contacts


@pytest.mark.asyncio
async def test_sms_plugin_execution():
    plugin = SMSPlugin()

    res_send = await plugin.execute("dev-a13", "sms.send", {"recipient": "+1234567890", "message": "Test SMS from Nova"})
    assert res_send["action"] == "sms.send"
    assert res_send["recipient"] == "+1234567890"

    res_read = await plugin.execute("dev-a13", "sms.read", {})
    assert res_read["action"] == "sms.read"


@pytest.mark.asyncio
async def test_call_plugin_execution():
    plugin = CallPlugin()

    res_make = await plugin.execute("dev-a13", "call.make", {"number": "+1987654321"})
    assert res_make["action"] == "call.make"
    assert res_make["number"] == "+1987654321"

    res_hist = await plugin.execute("dev-a13", "call.history", {"limit": 10})
    assert res_hist["action"] == "call.history"


@pytest.mark.asyncio
async def test_contacts_plugin_execution():
    plugin = ContactsPlugin()

    res_search = await plugin.execute("dev-a13", "contacts.search", {"query": "Rahul"})
    assert res_search["action"] == "contacts.search"
    assert res_search["query"] == "Rahul"


def test_otp_extraction_regex():
    import re
    otp_pattern = re.compile(r'(?i)(?:code|otp|pin|verify|verification|auth)[^\d]*(\d{4,8})')

    sample_sms1 = "Your Google verification code is 849201. Do not share it."
    match1 = otp_pattern.search(sample_sms1)
    assert match1 is not None
    assert match1.group(1) == "849201"

    sample_sms2 = "Use OTP 4921 to confirm your bank transaction."
    match2 = otp_pattern.search(sample_sms2)
    assert match2 is not None
    assert match2.group(1) == "4921"
