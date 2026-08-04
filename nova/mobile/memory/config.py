"""MemoryConfiguration & MemoryStatistics data models."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class MemoryConfiguration:
    auto_learn_contacts: bool = True
    auto_learn_apps: bool = True
    auto_learn_preferences: bool = True
    auto_learn_routines: bool = False    # explicit user confirmation required
    contact_frequency_threshold: int = 5
    app_frequency_threshold: int = 10
    command_frequency_threshold: int = 5
    preference_repeat_threshold: int = 3
    max_recent_commands: int = 50
    max_memory_entries: int = 1000
    encrypt_at_rest: bool = True
    sync_with_nova_core: bool = False    # opt-in only


@dataclass
class MemoryStatistics:
    total_entries: int = 0
    entries_by_category: Dict[str, int] = field(default_factory=dict)
    favorite_contacts_count: int = 0
    favorite_apps_count: int = 0
    frequent_commands_count: int = 0
    recent_commands_count: int = 0
    last_sync_timestamp: float = 0.0
