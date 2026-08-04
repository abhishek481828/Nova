"""SkillManifest — Declares skill metadata, permissions, and intent phrases."""

from dataclasses import dataclass, field
from typing import Set, List, Optional
from nova.mobile.skills.enums import SkillPermission, SkillCategory


@dataclass
class SkillManifest:
    skill_id: str
    name: str
    description: str
    version: str
    author: str
    category: SkillCategory
    permissions: Set[SkillPermission] = field(default_factory=set)
    supported_platforms: Set[str] = field(default_factory=lambda: {"ANDROID"})
    dependencies: List[str] = field(default_factory=list)
    min_nova_version: str = "3.0.0"
    max_nova_version: str = "4.0.0"
    entry_point: str = ""
    intent_phrases: List[str] = field(default_factory=list)
    is_first_party: bool = False
    is_enabled: bool = True

    def validate(self) -> tuple[bool, Optional[str]]:
        if not self.skill_id or not self.skill_id.strip():
            return False, "Skill ID must not be blank"
        if " " in self.skill_id:
            return False, "Skill ID must not contain spaces"
        if not self.name or not self.name.strip():
            return False, "Name must not be blank"
        if not self.version or not self.version.strip():
            return False, "Version must not be blank"
        if not self.author or not self.author.strip():
            return False, "Author must not be blank"
        return True, None
