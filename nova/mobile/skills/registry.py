"""SkillRegistry — Central store for installed skills and intent phrase index."""

import time
import logging
from typing import Dict, List, Optional, Set
from nova.mobile.skills.base_skill import BaseSkill
from nova.mobile.skills.enums import SkillStatus, SkillPermission

logger = logging.getLogger("nova.mobile.skills.registry")


class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._granted_permissions: Dict[str, Set[SkillPermission]] = {}
        self._intent_index: Dict[str, str] = {}  # phrase → skill_id
        self._audit_log: List[str] = []

    def register(self, skill: BaseSkill) -> bool:
        valid, err = skill.manifest.validate()
        if not valid:
            logger.error(f"Validation FAILED for '{skill.manifest.skill_id}': {err}")
            return False
        self._skills[skill.manifest.skill_id] = skill
        for phrase in skill.manifest.intent_phrases:
            self._intent_index[phrase.lower()] = skill.manifest.skill_id
        logger.info(f"Registered skill: '{skill.manifest.name}' v{skill.manifest.version}")
        return True

    def unregister(self, skill_id: str) -> bool:
        skill = self._skills.pop(skill_id, None)
        if not skill:
            return False
        for phrase in skill.manifest.intent_phrases:
            self._intent_index.pop(phrase.lower(), None)
        self._granted_permissions.pop(skill_id, None)
        logger.info(f"Unregistered skill: {skill_id}")
        return True

    def get(self, skill_id: str) -> Optional[BaseSkill]:
        return self._skills.get(skill_id)

    def get_all(self) -> List[BaseSkill]:
        return list(self._skills.values())

    def get_enabled(self) -> List[BaseSkill]:
        return [s for s in self._skills.values()
                if s.status in (SkillStatus.LOADED, SkillStatus.RUNNING)]

    def find_by_intent(self, text: str) -> Optional[BaseSkill]:
        low = text.lower()
        # Phrase match
        for phrase, skill_id in self._intent_index.items():
            if phrase in low:
                skill = self._skills.get(skill_id)
                if skill and skill.status in (SkillStatus.LOADED, SkillStatus.RUNNING):
                    return skill
        # Dynamic check
        for skill in self.get_enabled():
            if skill.can_handle(text):
                return skill
        return None

    def grant_permission(self, skill_id: str, permission: SkillPermission):
        self._granted_permissions.setdefault(skill_id, set()).add(permission)
        self._audit(f"GRANTED {permission.value} to '{skill_id}'")

    def revoke_permission(self, skill_id: str, permission: SkillPermission):
        if skill_id in self._granted_permissions:
            self._granted_permissions[skill_id].discard(permission)
            self._audit(f"REVOKED {permission.value} from '{skill_id}'")

    def get_granted_permissions(self, skill_id: str) -> Set[SkillPermission]:
        return set(self._granted_permissions.get(skill_id, set()))

    def count(self) -> int:
        return len(self._skills)

    def count_enabled(self) -> int:
        return len(self.get_enabled())

    def get_intent_index(self) -> Dict[str, str]:
        return dict(self._intent_index)

    def get_audit_log(self) -> List[str]:
        return list(self._audit_log)

    def _audit(self, message: str):
        entry = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {message}"
        self._audit_log.append(entry)
        logger.info(entry)
        if len(self._audit_log) > 500:
            self._audit_log.pop(0)
