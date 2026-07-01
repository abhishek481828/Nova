"""
Working Memory component for Nova AI Assistant.
Represents the short-term cognitive state, goals, context, and current execution trace.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Dict, List

from nova.logger import logger

@dataclass
class BrowserInfo:
    """
    Structured model representing the browser's current active state.
    """
    active_tab_url: Optional[str] = None
    active_tab_title: Optional[str] = None
    open_tabs_count: int = 0
    history_context: List[str] = field(default_factory=list)
    additional_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEvent:
    """
    Represents an internal cognitive or executor event with timestamp.
    """
    event_type: str
    message: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Interaction:
    """
    A single conversation turn between the user and assistant.
    """
    user_prompt: str
    assistant_response: str
    intent: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkingMemoryState:
    """
    The structured state container for Nova's short-term cognitive memory.
    """
    current_task: Optional[str] = None
    current_goal: Optional[str] = None
    conversation_context: Dict[str, Any] = field(default_factory=dict)
    previous_intent: Optional[str] = None
    previous_response: Optional[str] = None
    active_application: Optional[str] = None
    browser_information: Optional[BrowserInfo] = None
    temporary_execution_context: Dict[str, Any] = field(default_factory=dict)
    recent_actions: List[Dict[str, Any]] = field(default_factory=list)
    execution_status: str = "idle"
    conversation_topic: Optional[str] = None
    timestamped_events: List[MemoryEvent] = field(default_factory=list)
    conversation_history: List[Interaction] = field(default_factory=list)
    additional_properties: Dict[str, Any] = field(default_factory=dict)


class WorkingMemory:
    """
    WorkingMemory manager. Provides object-oriented APIs to store, retrieve,
    clear, and restore short-term cognitive states.
    """

    def __init__(self) -> None:
        self.state = WorkingMemoryState()
        logger.info("Working memory system initialized.")

    def set(self, key: str, value: Any) -> None:
        """
        Sets a value in working memory. If the key matches a predefined attribute in
        WorkingMemoryState, it updates the attribute directly. Otherwise, it stores
        it in additional_properties for extensibility.
        """
        if hasattr(self.state, key) and key != "additional_properties":
            setattr(self.state, key, value)
            logger.debug(f"State attribute updated: '{key}'", extra={"key": key, "value": value})
        else:
            self.state.additional_properties[key] = value
            logger.debug(f"Dynamic property updated: '{key}'", extra={"key": key, "value": value})

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a value by key. Looks up predefined state attributes first,
        then falls back to dynamic properties.
        """
        if hasattr(self.state, key) and key != "additional_properties":
            return getattr(self.state, key)
        return self.state.additional_properties.get(key, default)

    def remove(self, key: str) -> None:
        """
        Removes a key from working memory. If it is a predefined attribute, resets it to
        its default value. If it is a dynamic property, deletes it.
        """
        if hasattr(self.state, key) and key != "additional_properties":
            # Reset core attribute to default
            default_val = None
            if key == "conversation_context" or key == "temporary_execution_context":
                default_val = {}
            elif key == "recent_actions" or key == "timestamped_events" or key == "conversation_history":
                default_val = []
            elif key == "execution_status":
                default_val = "idle"
            setattr(self.state, key, default_val)
            logger.debug(f"State attribute reset: '{key}'", extra={"key": key})
        elif key in self.state.additional_properties:
            del self.state.additional_properties[key]
            logger.debug(f"Dynamic property removed: '{key}'", extra={"key": key})

    def clear(self) -> None:
        """
        Clears dynamic properties and resets all structured state attributes to defaults.
        """
        self.state = WorkingMemoryState()
        logger.info("Working memory successfully cleared.")

    def snapshot(self) -> Dict[str, Any]:
        """
        Serializes and returns a complete dictionary snapshot of the current state.
        This dictionary is fully JSON-serializable.
        """
        logger.info("Creating working memory snapshot.")
        return asdict(self.state)

    def restore(self, snapshot_data: Dict[str, Any]) -> None:
        """
        Restores working memory from a dictionary snapshot.
        Re-constructs all structured sub-dataclasses (BrowserInfo, MemoryEvent, Interaction).
        """
        if not isinstance(snapshot_data, dict):
            logger.error("Failed to restore memory snapshot: Invalid format.")
            raise ValueError("Snapshot data must be a dictionary.")

        new_state = WorkingMemoryState()
        new_state.current_task = snapshot_data.get("current_task")
        new_state.current_goal = snapshot_data.get("current_goal")
        new_state.conversation_context = dict(snapshot_data.get("conversation_context", {}))
        new_state.previous_intent = snapshot_data.get("previous_intent")
        new_state.previous_response = snapshot_data.get("previous_response")
        new_state.active_application = snapshot_data.get("active_application")
        new_state.execution_status = snapshot_data.get("execution_status", "idle")
        new_state.conversation_topic = snapshot_data.get("conversation_topic")
        new_state.temporary_execution_context = dict(snapshot_data.get("temporary_execution_context", {}))
        new_state.recent_actions = list(snapshot_data.get("recent_actions", []))

        # Reconstruct BrowserInfo
        browser_data = snapshot_data.get("browser_information")
        if browser_data is not None:
            new_state.browser_information = BrowserInfo(
                active_tab_url=browser_data.get("active_tab_url"),
                active_tab_title=browser_data.get("active_tab_title"),
                open_tabs_count=browser_data.get("open_tabs_count", 0),
                history_context=list(browser_data.get("history_context", [])),
                additional_metadata=dict(browser_data.get("additional_metadata", {}))
            )

        # Reconstruct MemoryEvents
        new_state.timestamped_events = [
            MemoryEvent(
                event_type=evt.get("event_type", "unknown"),
                message=evt.get("message", ""),
                timestamp=evt.get("timestamp", time.time()),
                metadata=dict(evt.get("metadata", {}))
            )
            for evt in snapshot_data.get("timestamped_events", [])
        ]

        # Reconstruct Interaction history
        new_state.conversation_history = [
            Interaction(
                user_prompt=inter.get("user_prompt", ""),
                assistant_response=inter.get("assistant_response", ""),
                intent=inter.get("intent"),
                timestamp=inter.get("timestamp", time.time()),
                metadata=dict(inter.get("metadata", {}))
            )
            for inter in snapshot_data.get("conversation_history", [])
        ]

        new_state.additional_properties = dict(snapshot_data.get("additional_properties", {}))
        self.state = new_state
        logger.info("Working memory successfully restored from snapshot.")

    def append_history(self, interaction: Dict[str, Any] | Interaction) -> None:
        """
        Appends a conversation turn to the interaction history.
        Accepts either an Interaction instance or a dict with user_prompt and assistant_response.
        """
        if isinstance(interaction, Interaction):
            self.state.conversation_history.append(interaction)
        elif isinstance(interaction, dict):
            user_prompt = interaction.get("user_prompt", "")
            assistant_response = interaction.get("assistant_response", "")
            intent = interaction.get("intent")
            timestamp = interaction.get("timestamp", time.time())
            metadata = interaction.get("metadata", {})
            self.state.conversation_history.append(
                Interaction(
                    user_prompt=user_prompt,
                    assistant_response=assistant_response,
                    intent=intent,
                    timestamp=timestamp,
                    metadata=metadata
                )
            )
        else:
            logger.error("Failed to append history: Invalid type.")
            raise TypeError("History record must be an Interaction or a dictionary.")

        logger.info("Appended interaction to conversation history.")

    def reset(self) -> None:
        """
        Resets working memory to a default clean state. Same as clear().
        """
        self.clear()
        logger.info("Working memory system reset.")
