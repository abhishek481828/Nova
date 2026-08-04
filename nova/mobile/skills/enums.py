"""Skill Enums — SkillPermission, SkillStatus, SkillCategory, SkillLifecycleEvent."""

from enum import Enum


class SkillPermission(str, Enum):
    CAMERA = "CAMERA"
    CONTACTS = "CONTACTS"
    SMS = "SMS"
    LOCATION = "LOCATION"
    MICROPHONE = "MICROPHONE"
    NOTIFICATIONS = "NOTIFICATIONS"
    STORAGE = "STORAGE"
    ACCESSIBILITY = "ACCESSIBILITY"
    NETWORK = "NETWORK"
    NOVA_CORE = "NOVA_CORE"
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    AUTOMATION = "AUTOMATION"
    SCHEDULER = "SCHEDULER"

    @property
    def requires_user_approval(self) -> bool:
        return self in {
            SkillPermission.CAMERA,
            SkillPermission.CONTACTS,
            SkillPermission.SMS,
            SkillPermission.LOCATION,
            SkillPermission.MICROPHONE,
            SkillPermission.ACCESSIBILITY,
        }


class SkillStatus(str, Enum):
    NOT_INSTALLED = "NOT_INSTALLED"
    INSTALLED = "INSTALLED"
    LOADING = "LOADING"
    LOADED = "LOADED"
    RUNNING = "RUNNING"
    DISABLED = "DISABLED"
    ERROR = "ERROR"
    UPDATING = "UPDATING"
    UNLOADING = "UNLOADING"


class SkillCategory(str, Enum):
    PRODUCTIVITY = "PRODUCTIVITY"
    COMMUNICATION = "COMMUNICATION"
    ENTERTAINMENT = "ENTERTAINMENT"
    UTILITIES = "UTILITIES"
    INFORMATION = "INFORMATION"
    HOME_AUTOMATION = "HOME_AUTOMATION"
    HEALTH = "HEALTH"
    NAVIGATION = "NAVIGATION"
    EDUCATION = "EDUCATION"
    FINANCE = "FINANCE"
    CUSTOM = "CUSTOM"


class SkillLifecycleEvent(str, Enum):
    INSTALLED = "SkillInstalled"
    LOADED = "SkillLoaded"
    ENABLED = "SkillEnabled"
    DISABLED = "SkillDisabled"
    UNLOADED = "SkillUnloaded"
    REMOVED = "SkillRemoved"
    UPDATED = "SkillUpdated"
    ERROR = "SkillError"
    PERMISSION_GRANTED = "SkillPermissionGranted"
    PERMISSION_DENIED = "SkillPermissionDenied"
