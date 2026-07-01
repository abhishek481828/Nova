"""
Working Memory component for Nova AI Assistant.
Represents the short-term cognitive state, goals, context, and current execution trace.
Includes a dedicated Session State layer, Context Manager, and History Manager.
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
class MemoryContext:
    """
    Represents a specific runtime focus or workspace context.
    """
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class HistoryEntry:
    """
    Structured short-term log entry tracking various system activities.
    """
    event_type: str  # user_interaction, assistant_response, action_execution, browser_event, voice_event, system_event
    message: str
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
    
    # Nested runtime Session State
    session_state: SessionState = field(default_factory=SessionState)

    # Nested Context Manager states
    active_contexts: List[MemoryContext] = field(default_factory=list)
    previous_context: Optional[MemoryContext] = None

    # Nested History Manager states
    history_entries: List[HistoryEntry] = field(default_factory=list)


class TemporaryContext:
    """
    Helper wrapper for 'with' statement scopes.
    """
    def __init__(self, manager: MemoryContextManager, name: str, metadata: Optional[Dict[str, Any]] = None):
        self.manager = manager
        self.name = name
        self.metadata = metadata or {}
        self.context = None

    def __enter__(self) -> MemoryContext:
        self.context = self.manager.enter_context(self.name, self.metadata)
        return self.context

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.manager.exit_context(self.name)


class MemoryContextManager:
    """
    Coordinates entering, exiting, switching, and restoring cognitive context scopes.
    """
    def __init__(self, wm: WorkingMemory):
        self.wm = wm

    @property
    def current_context(self) -> Optional[MemoryContext]:
        if self.wm.state.active_contexts:
            return self.wm.state.active_contexts[-1]
        return None

    @property
    def previous_context(self) -> Optional[MemoryContext]:
        return self.wm.state.previous_context

    @previous_context.setter
    def previous_context(self, val: Optional[MemoryContext]) -> None:
        self.wm.state.previous_context = val

    def enter_context(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> MemoryContext:
        """Pushes a new context onto the stack, making it active."""
        ctx = MemoryContext(name=name, metadata=metadata or {})
        self.wm.state.active_contexts.append(ctx)
        logger.info(f"Entered context: '{name}'")
        return ctx

    def exit_context(self, name: Optional[str] = None) -> Optional[MemoryContext]:
        """Pops the active context from the stack and sets it as the previous context."""
        if not self.wm.state.active_contexts:
            logger.warning("Attempted to exit context from an empty stack.")
            return None
        
        ctx = self.wm.state.active_contexts[-1]
        if name is not None and ctx.name != name:
            logger.warning(f"Exiting context mismatch: expected '{name}', got '{ctx.name}'")
            
        popped = self.wm.state.active_contexts.pop()
        self.previous_context = popped
        logger.info(f"Exited context: '{popped.name}'")
        return popped

    def switch_context(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> MemoryContext:
        """Switches the active context by replacing the top of the stack."""
        if self.wm.state.active_contexts:
            self.previous_context = self.wm.state.active_contexts.pop()
        ctx = MemoryContext(name=name, metadata=metadata or {})
        self.wm.state.active_contexts.append(ctx)
        logger.info(f"Switched context to: '{name}'")
        return ctx

    def clear_contexts(self) -> None:
        """Wipes the context stack and previous context history."""
        self.wm.state.active_contexts.clear()
        self.previous_context = None
        logger.info("Cleared all contexts.")

    def restore_context(self) -> Optional[MemoryContext]:
        """Pushes the previous context back onto the stack."""
        if self.previous_context is None:
            logger.warning("No previous context available to restore.")
            return None
        ctx = self.previous_context
        self.wm.state.active_contexts.append(ctx)
        self.previous_context = None
        logger.info(f"Restored context: '{ctx.name}'")
        return ctx

    def temporary(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> TemporaryContext:
        """Returns a TemporaryContext wrapper for block-scoped with statements."""
        return TemporaryContext(self, name, metadata)


class MemoryHistoryManager:
    """
    Maintains a sliding window of chronological short-term event records.
    """
    def __init__(self, wm: WorkingMemory, limit: int = 100):
        self.wm = wm
        self.limit = limit

    def add_entry(self, event_type: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> HistoryEntry:
        """Appends a log record and keeps list within configured limits."""
        entry = HistoryEntry(event_type=event_type, message=message, metadata=metadata or {})
        
        # Pull history list from State
        history = list(self.wm.get("history_entries") or [])
        history.append(entry)
        
        # Enforce capacity
        if len(history) > self.limit:
            history.pop(0)
            
        self.wm.set("history_entries", history)
        logger.info(f"Added history entry: [{event_type}] {message}")
        return entry

    def get_entries(self, event_type: Optional[str] = None) -> List[HistoryEntry]:
        """Retrieves history logs, optionally filtered by event type."""
        entries = list(self.wm.get("history_entries") or [])
        if event_type is not None:
            return [e for e in entries if e.event_type == event_type]
        return entries


class WorkingMemory:
    """
    WorkingMemory manager. Provides object-oriented APIs to store, retrieve,
    clear, and restore short-term cognitive states and runtime sessions.
    """

    def __init__(self, history_limit: int = 100) -> None:
        self.state = WorkingMemoryState()
        self.context_manager = MemoryContextManager(self)
        self.history_manager = MemoryHistoryManager(self, limit=history_limit)
        
        # Register the default memory instance onto BaseAction class
        try:
            from nova.actions.base import BaseAction
            BaseAction._shared_working_memory = self
        except Exception:
            pass
        logger.info("Working memory system initialized.")

    def log_system_event(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> HistoryEntry:
        """Utility wrapper to log generic system events."""
        return self.history_manager.add_entry("system_event", message, metadata)

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
            if key == "recent_actions":
                if not isinstance(value, list):
                    raise TypeError("recent_actions must be a list.")
                for item in value:
                    if not isinstance(item, dict):
                        raise TypeError("All items in recent_actions must be dictionaries.")
            elif key == "active_contexts":
                if not isinstance(value, list):
                    raise TypeError("active_contexts must be a list.")
                for item in value:
                    if not isinstance(item, MemoryContext):
                        raise TypeError("All items in active_contexts must be MemoryContext objects.")
            elif key == "previous_context":
                if value is not None and not isinstance(value, MemoryContext):
                    raise TypeError("previous_context must be a MemoryContext object or None.")
            elif key == "history_entries":
                if not isinstance(value, list):
                    raise TypeError("history_entries must be a list.")
                for item in value:
                    if not isinstance(item, HistoryEntry):
                        raise TypeError("All items in history_entries must be HistoryEntry objects.")
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
            elif key == "active_contexts":
                default_val = []
            elif key == "previous_context":
                default_val = None
            elif key == "history_entries":
                default_val = []
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

        # Reconstruct active_contexts
        new_state.active_contexts = [
            MemoryContext(
                name=c.get("name"),
                metadata=dict(c.get("metadata", {})),
                timestamp=c.get("timestamp", time.time())
            )
            for c in snapshot_data.get("active_contexts", [])
        ]
        
        # Reconstruct previous_context
        prev_c = snapshot_data.get("previous_context")
        if prev_c is not None:
            new_state.previous_context = MemoryContext(
                name=prev_c.get("name"),
                metadata=dict(prev_c.get("metadata", {})),
                timestamp=prev_c.get("timestamp", time.time())
            )

        # Reconstruct history_entries
        new_state.history_entries = [
            HistoryEntry(
                event_type=h.get("event_type", "system_event"),
                message=h.get("message", ""),
                timestamp=h.get("timestamp", time.time()),
                metadata=dict(h.get("metadata", {}))
            )
            for h in snapshot_data.get("history_entries", [])
        ]

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
            user_prompt = interaction.user_prompt
            assistant_response = interaction.assistant_response
            intent = interaction.intent
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

        # Log to Unified History Manager
        self.history_manager.add_entry("user_interaction", f"User: {user_prompt}", {"intent": intent})
        self.history_manager.add_entry("assistant_response", f"Assistant: {assistant_response}", {"intent": intent})

        logger.info("Appended interaction to conversation history.")

    def reset(self) -> None:
        """
        Resets working memory to a default clean state. Same as clear().
        """
        self.clear()
        logger.info("Working memory system reset.")
