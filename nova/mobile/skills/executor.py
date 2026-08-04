"""SkillExecutor — Routes voice queries to matching skills."""

import time
import logging
from typing import List, Optional
from nova.mobile.skills.base_skill import SkillExecutionResult
from nova.mobile.skills.enums import SkillStatus
from nova.mobile.skills.registry import SkillRegistry

logger = logging.getLogger("nova.mobile.skills.executor")


class SkillExecutor:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self._history: List[SkillExecutionResult] = []

    def execute(self, text: str) -> Optional[SkillExecutionResult]:
        skill = self.registry.find_by_intent(text)
        if not skill:
            logger.debug(f"No skill matched for: '{text}'")
            return None

        if skill.status != SkillStatus.RUNNING:
            logger.warning(f"Skill '{skill.manifest.skill_id}' matched but status is {skill.status.value}")
            return None

        start = time.time()
        logger.info(f"→ Executing '{skill.manifest.name}' for: '{text}'")

        try:
            result = skill.execute(text)
        except Exception as e:
            logger.error(f"Skill '{skill.manifest.skill_id}' failed: {e}", exc_info=True)
            result = SkillExecutionResult(
                skill_id=skill.manifest.skill_id,
                is_success=False,
                spoken_response=f"Sorry, the {skill.manifest.name} skill encountered an error.",
                error_message=str(e),
                duration_ms=int((time.time() - start) * 1000)
            )

        result.duration_ms = int((time.time() - start) * 1000)
        self._record(result)
        logger.info(f"← '{skill.manifest.name}' finished in {result.duration_ms}ms [{'OK' if result.is_success else 'FAIL'}]")
        return result

    def get_history(self) -> List[SkillExecutionResult]:
        return list(reversed(self._history))

    def get_last_result(self) -> Optional[SkillExecutionResult]:
        return self._history[-1] if self._history else None

    def total_executions(self) -> int:
        return len(self._history)

    def failure_count(self) -> int:
        return sum(1 for r in self._history if not r.is_success)

    def _record(self, result: SkillExecutionResult):
        self._history.append(result)
        if len(self._history) > 200:
            self._history.pop(0)
