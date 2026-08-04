"""SkillLoader — Skill lifecycle state machine."""

import logging
from nova.mobile.skills.base_skill import BaseSkill
from nova.mobile.skills.context import SkillContext
from nova.mobile.skills.enums import SkillStatus
from nova.mobile.skills.registry import SkillRegistry

logger = logging.getLogger("nova.mobile.skills.loader")


class SkillLoader:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def install(self, skill: BaseSkill, context: SkillContext) -> bool:
        skill.context = context
        skill.status = SkillStatus.INSTALLED
        return self.registry.register(skill)

    def load(self, skill_id: str) -> bool:
        skill = self.registry.get(skill_id)
        if not skill:
            return False
        if skill.status in (SkillStatus.LOADED, SkillStatus.RUNNING):
            return True
        try:
            skill.status = SkillStatus.LOADING
            skill.on_create()
            skill.status = SkillStatus.LOADED
            logger.info(f"Loaded: '{skill.manifest.name}'")
            return True
        except Exception as e:
            skill.status = SkillStatus.ERROR
            logger.error(f"Failed to load '{skill_id}': {e}", exc_info=True)
            return False

    def enable(self, skill_id: str) -> bool:
        skill = self.registry.get(skill_id)
        if not skill:
            return False
        if skill.status == SkillStatus.RUNNING:
            return True
        try:
            skill.on_enable()
            skill.status = SkillStatus.RUNNING
            logger.info(f"Enabled: '{skill.manifest.name}'")
            return True
        except Exception as e:
            skill.status = SkillStatus.ERROR
            logger.error(f"Failed to enable '{skill_id}': {e}", exc_info=True)
            return False

    def disable(self, skill_id: str) -> bool:
        skill = self.registry.get(skill_id)
        if not skill:
            return False
        try:
            skill.on_disable()
            skill.status = SkillStatus.DISABLED
            logger.info(f"Disabled: '{skill.manifest.name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to disable '{skill_id}': {e}", exc_info=True)
            return False

    def unload(self, skill_id: str) -> bool:
        skill = self.registry.get(skill_id)
        if not skill:
            return False
        try:
            skill.status = SkillStatus.UNLOADING
            skill.on_destroy()
            self.registry.unregister(skill_id)
            logger.info(f"Unloaded: '{skill_id}'")
            return True
        except Exception as e:
            skill.status = SkillStatus.ERROR
            logger.error(f"Failed to unload '{skill_id}': {e}", exc_info=True)
            return False

    def hot_reload(self, skill: BaseSkill, context: SkillContext) -> bool:
        sid = skill.manifest.skill_id
        logger.info(f"Hot-reloading: '{sid}'")
        self.unload(sid)
        return self.install(skill, context) and self.load(sid) and self.enable(sid)
