"""SkillContext — Sandboxed API surface provided to skills."""

from typing import Set, Optional, Callable
from nova.mobile.skills.enums import SkillPermission


class SkillMemoryApi:
    def remember(self, key: str, value: str): pass
    def recall(self, key: str) -> Optional[str]: return None
    def forget(self, key: str): pass


class SkillNotificationApi:
    def notify(self, title: str, body: str): pass


class SkillSchedulerApi:
    def schedule_once(self, delay_ms: int, action: Callable): pass


class SkillVoiceApi:
    def speak(self, text: str): pass


class SkillContext:
    def __init__(
        self,
        skill_id: str,
        granted_permissions: Set[SkillPermission],
        memory_api: Optional[SkillMemoryApi] = None,
        notification_api: Optional[SkillNotificationApi] = None,
        scheduler_api: Optional[SkillSchedulerApi] = None,
        voice_api: Optional[SkillVoiceApi] = None
    ):
        self.skill_id = skill_id
        self._granted_permissions = set(granted_permissions)
        self.memory_api = memory_api
        self.notification_api = notification_api
        self.scheduler_api = scheduler_api
        self.voice_api = voice_api

    def has_permission(self, permission: SkillPermission) -> bool:
        return permission in self._granted_permissions

    def require_permission(self, permission: SkillPermission):
        if not self.has_permission(permission):
            raise PermissionError(f"Skill '{self.skill_id}' missing permission: {permission.value}")
