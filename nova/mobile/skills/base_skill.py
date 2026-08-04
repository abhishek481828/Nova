"""BaseSkill — Abstract base class for all Nova skills."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from nova.mobile.skills.manifest import SkillManifest
from nova.mobile.skills.context import SkillContext
from nova.mobile.skills.enums import SkillStatus


@dataclass
class SkillExecutionResult:
    skill_id: str
    is_success: bool
    spoken_response: str
    error_message: Optional[str] = None
    duration_ms: int = 0


class BaseSkill(ABC):
    @property
    @abstractmethod
    def manifest(self) -> SkillManifest:
        pass

    def __init__(self):
        self.context: Optional[SkillContext] = None
        self.status: SkillStatus = SkillStatus.NOT_INSTALLED

    def on_create(self): pass
    def on_enable(self): pass
    def on_disable(self): pass
    def on_destroy(self): pass

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        pass

    @abstractmethod
    def execute(self, text: str) -> SkillExecutionResult:
        pass
