"""
Working Memory component for Nova AI Assistant.
Represents the short-term cognitive state, goals, context, and current execution trace.
Includes a dedicated Session State layer for runtime context management.
"""

from __future__ import annotations

import time
import logging
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Dict, List

from nova.logger import logger

# Allowed values for runtime execution status
VALID_STATUSES = {"idle", "running", "paused", "completed", "failed", "aborted"}


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
class SessionState:
    """
    Manages Nova's current runtime session state.
    Provides validation constraints for runtime fields.
    """
    session_identifier: str = field(default_factory=lambda: f"session_{uuid.uuid4()}")
    session_start_time: float = field(default_factory=time.time)
    current_execution_status: str = "idle"
    current_conversation: List[Interaction] = field(default_factory=list)
    active_task: Optional[str] = None
    active_goal: Optional[str] = None
    current_application: Optional[str] = None
    current_browser: Optional[str] = None
    current_website: Optional[str] = None
    current_webpage: Optional[str] = None
    current_search_query: Optional[str] = None
    previous_command: Optional[str] = None
    previous_assistant_reply: Optional[str] = None
    conversation_topic: Optional[str] = None

    # Voice pipeline properties
    voice_session_state: Optional[str] = "inactive"
    listening_state: Optional[str] = "idle"
    wake_word_activation: Optional[bool] = False
    recognition_confidence: Optional[float] = 0.0
    current_speaker: Optional[str] = None
    final_transcription: Optional[str] = None

    # Browser integration properties
    current_tab: Optional[str] = None
    tab_title: Optional[str] = None
    current_url: Optional[str] = None
    domain: Optional[str] = None
    search_engine: Optional[str] = None
    navigation_history: List[str] = field(default_factory=list)
    download_activity: List[Dict[str, Any]] = field(default_factory=list)
    open_tabs_count: int = 0

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """
        Validates the session state attributes.
        Raises ValueError or TypeError if validation fails.
        """
        # Validate session_identifier
        if not isinstance(self.session_identifier, str) or not self.session_identifier.strip():
            raise ValueError("session_identifier must be a non-empty string.")

        # Validate session_start_time
        if not isinstance(self.session_start_time, (int, float)) or self.session_start_time <= 0:
            raise ValueError("session_start_time must be a positive number.")

        # Validate execution status
        if self.current_execution_status not in VALID_STATUSES:
            raise ValueError(
                f"current_execution_status must be one of {VALID_STATUSES}, got '{self.current_execution_status}'"
            )

        # Validate conversation is list of Interaction objects
        if not isinstance(self.current_conversation, list):
            raise TypeError("current_conversation must be a list.")
        for item in self.current_conversation:
            if not isinstance(item, Interaction):
                raise TypeError("All items in current_conversation must be Interaction objects.")

        # Validate voice integration properties
        if self.voice_session_state not in {None, "active", "inactive", "idle"}:
            raise ValueError(
                f"voice_session_state must be one of {{'active', 'inactive', 'idle'}}, got '{self.voice_session_state}'"
            )
        if self.listening_state not in {None, "idle", "listening"}:
            raise ValueError(
                f"listening_state must be one of {{'idle', 'listening'}}, got '{self.listening_state}'"
            )
        if self.recognition_confidence is not None and (
            not isinstance(self.recognition_confidence, (int, float)) or not (0.0 <= self.recognition_confidence <= 1.0)
        ):
            raise ValueError("recognition_confidence must be between 0.0 and 1.0.")

        # Validate browser properties
        if not isinstance(self.open_tabs_count, int) or self.open_tabs_count < 0:
            raise ValueError("open_tabs_count must be a non-negative integer.")
        if not isinstance(self.navigation_history, list):
            raise TypeError("navigation_history must be a list.")
        for item in self.navigation_history:
            if not isinstance(item, str):
                raise TypeError("All items in navigation_history must be strings.")
        if not isinstance(self.download_activity, list):
            raise TypeError("download_activity must be a list.")
        for item in self.download_activity:
            if not isinstance(item, dict):
                raise TypeError("All items in download_activity must be dictionaries.")


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
    
    # Nested runtime Session State
    session_state: SessionState = field(default_factory=SessionState)


class WorkingMemory:
    """
    WorkingMemory manager. Provides object-oriented APIs to store, retrieve,
    clear, and restore short-term cognitive states and runtime sessions.
    """

    def __init__(self) -> None:
        self.state = WorkingMemoryState()
        logger.info("Working memory system initialized.")

    def set(self, key: str, value: Any) -> None:
        """
        Sets a value in working memory. If the key matches a predefined attribute in
        SessionState or WorkingMemoryState, it updates the attribute directly and validates.
        Otherwise, it stores it in additional_properties for extensibility.
        """
        if hasattr(self.state.session_state, key):
            orig_val = getattr(self.state.session_state, key)
            try:
                setattr(self.state.session_state, key, value)
                self.state.session_state.validate()
                logger.debug(f"Session state attribute updated: '{key}'", extra={"key": key, "value": value})
            except Exception as e:
                # Rollback changes to preserve validation state consistency
                setattr(self.state.session_state, key, orig_val)
                logger.error(f"Validation failed for session state key '{key}': {e}")
                raise e
        elif hasattr(self.state, key) and key != "additional_properties" and key != "session_state":
            setattr(self.state, key, value)
            logger.debug(f"State attribute updated: '{key}'", extra={"key": key, "value": value})
        else:
            self.state.additional_properties[key] = value
            logger.debug(f"Dynamic property updated: '{key}'", extra={"key": key, "value": value})

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a value by key. Looks up SessionState attributes first,
        then predefined state attributes, then falls back to dynamic properties.
        """
        if hasattr(self.state.session_state, key):
            return getattr(self.state.session_state, key)
        if hasattr(self.state, key) and key != "additional_properties" and key != "session_state":
            return getattr(self.state, key)
        return self.state.additional_properties.get(key, default)

    def remove(self, key: str) -> None:
        """
        Removes a key from working memory. Resets it to its default value if it is predefined
        in SessionState or WorkingMemoryState. Deletes it if it is a dynamic property.
        """
        if hasattr(self.state.session_state, key):
            default_val = None
            if key == "current_conversation":
                default_val = []
            elif key == "current_execution_status":
                default_val = "idle"
            elif key == "session_identifier":
                default_val = f"session_{uuid.uuid4()}"
            elif key == "session_start_time":
                default_val = time.time()
            elif key == "voice_session_state":
                default_val = "inactive"
            elif key == "listening_state":
                default_val = "idle"
            elif key == "wake_word_activation":
                default_val = False
            elif key == "recognition_confidence":
                default_val = 0.0
            elif key == "navigation_history":
                default_val = []
            elif key == "download_activity":
                default_val = []
            elif key == "open_tabs_count":
                default_val = 0
            setattr(self.state.session_state, key, default_val)
            self.state.session_state.validate()
            logger.debug(f"Session state attribute reset: '{key}'", extra={"key": key})
        elif hasattr(self.state, key) and key != "additional_properties" and key != "session_state":
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
        Clears dynamic properties and resets all structured state and session attributes.
        """
        self.state = WorkingMemoryState()
        logger.info("Working memory successfully cleared.")

    def snapshot(self) -> Dict[str, Any]:
        """
        Serializes and returns a complete dictionary snapshot of the current state and session.
        This dictionary is fully JSON-serializable.
        """
        logger.info("Creating working memory snapshot.")
        return asdict(self.state)

    def restore(self, snapshot_data: Dict[str, Any]) -> None:
        """
        Restores working memory and session from a dictionary snapshot.
        Re-constructs all structured sub-dataclasses (BrowserInfo, MemoryEvent, Interaction, SessionState).
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

        # Reconstruct SessionState
        session_data = snapshot_data.get("session_state", {})
        session_conv = [
            Interaction(
                user_prompt=inter.get("user_prompt", ""),
                assistant_response=inter.get("assistant_response", ""),
                intent=inter.get("intent"),
                timestamp=inter.get("timestamp", time.time()),
                metadata=dict(inter.get("metadata", {}))
            )
            for inter in session_data.get("current_conversation", [])
        ]
        new_state.session_state = SessionState(
            session_identifier=session_data.get("session_identifier", f"session_{uuid.uuid4()}"),
            session_start_time=session_data.get("session_start_time", time.time()),
            current_execution_status=session_data.get("current_execution_status", "idle"),
            current_conversation=session_conv,
            active_task=session_data.get("active_task"),
            active_goal=session_data.get("active_goal"),
            current_application=session_data.get("current_application"),
            current_browser=session_data.get("current_browser"),
            current_website=session_data.get("current_website"),
            current_webpage=session_data.get("current_webpage"),
            current_search_query=session_data.get("current_search_query"),
            previous_command=session_data.get("previous_command"),
            previous_assistant_reply=session_data.get("previous_assistant_reply"),
            conversation_topic=session_data.get("conversation_topic"),
            voice_session_state=session_data.get("voice_session_state", "inactive"),
            listening_state=session_data.get("listening_state", "idle"),
            wake_word_activation=session_data.get("wake_word_activation", False),
            recognition_confidence=session_data.get("recognition_confidence", 0.0),
            current_speaker=session_data.get("current_speaker"),
            final_transcription=session_data.get("final_transcription"),
            current_tab=session_data.get("current_tab"),
            tab_title=session_data.get("tab_title"),
            current_url=session_data.get("current_url"),
            domain=session_data.get("domain"),
            search_engine=session_data.get("search_engine"),
            navigation_history=list(session_data.get("navigation_history", [])),
            download_activity=list(session_data.get("download_activity", [])),
            open_tabs_count=session_data.get("open_tabs_count", 0),
        )

        new_state.additional_properties = dict(snapshot_data.get("additional_properties", {}))
        self.state = new_state
        logger.info("Working memory and session successfully restored from snapshot.")

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
