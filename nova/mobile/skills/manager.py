"""SkillManager — Phase 9 Main Orchestrator."""

import logging
from typing import Dict, List, Optional, Set
from nova.mobile.skills.enums import SkillPermission, SkillLifecycleEvent
from nova.mobile.skills.base_skill import BaseSkill, SkillExecutionResult
from nova.mobile.skills.context import (
    SkillContext, SkillMemoryApi, SkillNotificationApi,
    SkillSchedulerApi, SkillVoiceApi
)
from nova.mobile.skills.registry import SkillRegistry
from nova.mobile.skills.loader import SkillLoader
from nova.mobile.skills.executor import SkillExecutor

logger = logging.getLogger("nova.mobile.skills.manager")


class SkillManager:
    def __init__(self, lifecycle_manager=None):
        self._lifecycle_manager = lifecycle_manager
        self.registry = SkillRegistry()
        self.loader = SkillLoader(self.registry)
        self.executor = SkillExecutor(self.registry)

        self._pending_permissions: Dict[str, Set[SkillPermission]] = {}
        self.memory_api: Optional[SkillMemoryApi] = None
        self.notification_api: Optional[SkillNotificationApi] = None
        self.scheduler_api: Optional[SkillSchedulerApi] = None
        self.voice_api: Optional[SkillVoiceApi] = None

    def set_memory_api(self, api: SkillMemoryApi): self.memory_api = api
    def set_notification_api(self, api: SkillNotificationApi): self.notification_api = api
    def set_scheduler_api(self, api: SkillSchedulerApi): self.scheduler_api = api
    def set_voice_api(self, api: SkillVoiceApi): self.voice_api = api

    def install_and_load(self, skill: BaseSkill) -> bool:
        valid, err = skill.manifest.validate()
        if not valid:
            logger.error(f"Rejected invalid skill: {err}")
            return False

        granted = self._process_permissions(skill)
        context = SkillContext(
            skill_id=skill.manifest.skill_id,
            granted_permissions=granted,
            memory_api=self.memory_api,
            notification_api=self.notification_api,
            scheduler_api=self.scheduler_api,
            voice_api=self.voice_api
        )

        if not self.loader.install(skill, context):
            return False
        if not self.loader.load(skill.manifest.skill_id):
            return False
        enabled = self.loader.enable(skill.manifest.skill_id)

        self._publish(SkillLifecycleEvent.INSTALLED,
                      {"skillId": skill.manifest.skill_id, "name": skill.manifest.name})
        logger.info(f"Skill fully installed and running: '{skill.manifest.name}'")
        return enabled

    def remove(self, skill_id: str) -> bool:
        ok = self.loader.unload(skill_id)
        if ok:
            self._publish(SkillLifecycleEvent.REMOVED, {"skillId": skill_id})
        return ok

    def enable(self, skill_id: str) -> bool:
        ok = self.loader.enable(skill_id)
        if ok:
            self._publish(SkillLifecycleEvent.ENABLED, {"skillId": skill_id})
        return ok

    def disable(self, skill_id: str) -> bool:
        ok = self.loader.disable(skill_id)
        if ok:
            self._publish(SkillLifecycleEvent.DISABLED, {"skillId": skill_id})
        return ok

    def handle_voice_text(self, text: str) -> Optional[SkillExecutionResult]:
        return self.executor.execute(text)

    def _process_permissions(self, skill: BaseSkill) -> Set[SkillPermission]:
        granted = set()
        for perm in skill.manifest.permissions:
            if perm.requires_user_approval:
                self._pending_permissions.setdefault(skill.manifest.skill_id, set()).add(perm)
                logger.info(f"Permission '{perm.value}' for '{skill.manifest.name}' requires user approval")
            else:
                granted.add(perm)
                self.registry.grant_permission(skill.manifest.skill_id, perm)
        return granted

    def approve_permission(self, skill_id: str, permission: SkillPermission) -> bool:
        self.registry.grant_permission(skill_id, permission)
        if skill_id in self._pending_permissions:
            self._pending_permissions[skill_id].discard(permission)
        self._publish(SkillLifecycleEvent.PERMISSION_GRANTED,
                      {"skillId": skill_id, "permission": permission.value})
        return True

    def deny_permission(self, skill_id: str, permission: SkillPermission):
        if skill_id in self._pending_permissions:
            self._pending_permissions[skill_id].discard(permission)
        self._publish(SkillLifecycleEvent.PERMISSION_DENIED,
                      {"skillId": skill_id, "permission": permission.value})

    def get_pending_permissions(self) -> Dict[str, Set[SkillPermission]]:
        return {k: set(v) for k, v in self._pending_permissions.items() if v}

    def search_skills(self, query: str) -> List[BaseSkill]:
        q = query.lower()
        return [s for s in self.registry.get_all()
                if q in s.manifest.name.lower() or
                q in s.manifest.description.lower() or
                q in s.manifest.category.value.lower()]

    def get_stats(self) -> dict:
        return {
            "total_skills": self.registry.count(),
            "running_skills": self.registry.count_enabled(),
            "total_executions": self.executor.total_executions(),
            "failed_executions": self.executor.failure_count(),
            "registered_intents": len(self.registry.get_intent_index()),
            "pending_permissions": sum(len(v) for v in self._pending_permissions.values())
        }

    def _publish(self, event: SkillLifecycleEvent, payload: dict):
        if self._lifecycle_manager:
            self._lifecycle_manager.publish_event(event.value, payload)
