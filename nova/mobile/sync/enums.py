"""Sync Enums — Platform, DeviceStatus, ConflictPolicy, SyncEvent, SyncCategory."""

from enum import Enum


class Platform(str, Enum):
    ANDROID = "ANDROID"
    NOVA_CORE = "NOVA_CORE"
    TABLET = "TABLET"
    SMARTWATCH = "SMARTWATCH"
    CLOUD_FUTURE = "CLOUD_FUTURE"


class DeviceStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHENTICATED = "UNAUTHENTICATED"


class ConflictPolicy(str, Enum):
    NEWEST_WINS = "NEWEST_WINS"
    OLDEST_WINS = "OLDEST_WINS"
    PHONE_WINS = "PHONE_WINS"
    NOVA_CORE_WINS = "NOVA_CORE_WINS"
    USER_CONFIRM = "USER_CONFIRM"


class SyncEvent(str, Enum):
    DEVICE_JOINED = "DeviceJoined"
    DEVICE_LEFT = "DeviceLeft"
    SYNC_STARTED = "SyncStarted"
    SYNC_COMPLETED = "SyncCompleted"
    SYNC_FAILED = "SyncFailed"
    SYNC_RESTORED = "SyncRestored"
    CONFLICT_DETECTED = "ConflictDetected"
    CONFLICT_RESOLVED = "ConflictResolved"
    DEVICE_AUTHENTICATED = "DeviceAuthenticated"
    DEVICE_UNAUTHENTICATED = "DeviceUnauthenticated"


class SyncCategory(str, Enum):
    PREFERENCES = "PREFERENCES"
    FAVORITE_CONTACTS = "FAVORITE_CONTACTS"
    FAVORITE_APPS = "FAVORITE_APPS"
    RECENT_COMMANDS = "RECENT_COMMANDS"
    ROUTINE_DEFINITIONS = "ROUTINE_DEFINITIONS"
    TRUSTED_DEVICES = "TRUSTED_DEVICES"
    SESSION_STATE = "SESSION_STATE"
    CONFIGURATION = "CONFIGURATION"
