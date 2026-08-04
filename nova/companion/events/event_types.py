"""Standard Event Types for Nova v2.0."""

from enum import Enum


class EventType(str, Enum):
    # Device lifecycle
    DEVICE_CONNECTED = "device.connected"
    DEVICE_DISCONNECTED = "device.disconnected"
    DEVICE_CAPABILITIES_ADVERTISED = "device.capabilities_advertised"
    
    # Telemetry
    BATTERY_CHANGED = "battery.changed"
    BATTERY_LOW = "battery.low"
    WIFI_CHANGED = "wifi.changed"
    LOCATION_UPDATED = "location.updated"

    # Notifications & Messages
    NOTIFICATION_RECEIVED = "notification.received"
    SMS_RECEIVED = "sms.received"
    INCOMING_CALL = "call.incoming"

    # UI & Accessibility
    SCREEN_STATE_CHANGED = "screen.state_changed"
    ACCESSIBILITY_ACTION_PERFORMED = "accessibility.action_performed"


class CompanionEvent:
    """Represents a companion event message payload."""

    def __init__(self, event_type: str, device_id: str, payload: dict = None, timestamp: float = None):
        self.event_type = event_type
        self.device_id = device_id
        self.payload = payload or {}
        self.timestamp = timestamp or 0.0
