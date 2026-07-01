from __future__ import annotations

import time
import logging
import uuid
import threading
import sqlite3
import json
import math
import re
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Dict, List

from nova.logger import logger, log_error, log_command
from nova.config import HISTORY_JSON_PATH
from nova.core.context import BrowserInfo, MemoryContext, MemoryContextManager

# Allowed values for runtime execution status
VALID_STATUSES = {"idle", "running", "paused", "completed", "failed", "aborted"}


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
        if not isinstance(self.session_identifier, str) or not self.session_identifier.strip():
            raise ValueError("session_identifier must be a non-empty string.")

        if not isinstance(self.session_start_time, (int, float)) or self.session_start_time <= 0:
            raise ValueError("session_start_time must be a positive number.")

        if self.current_execution_status not in VALID_STATUSES:
            raise ValueError(
                f"current_execution_status must be one of {VALID_STATUSES}, got '{self.current_execution_status}'"
            )

        if not isinstance(self.current_conversation, list):
            raise TypeError("current_conversation must be a list.")
        for item in self.current_conversation:
            if not isinstance(item, Interaction):
                raise TypeError("All items in current_conversation must be Interaction objects.")

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


class MemoryHistoryManager:
    """
    Maintains a sliding window of chronological short-term event records with thread safety.
    """
    def __init__(self, wm: WorkingMemory, limit: int = 100):
        self.wm = wm
        self.limit = limit

    def add_entry(self, event_type: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> HistoryEntry:
        """Appends a log record and keeps list within configured limits."""
        with self.wm._lock:
            entry = HistoryEntry(event_type=event_type, message=message, metadata=metadata or {})
            history = list(self.wm.get("history_entries") or [])
            history.append(entry)
            if len(history) > self.limit:
                history.pop(0)
            self.wm.set("history_entries", history)
            logger.info(f"Added history entry: [{event_type}] {message}")
            return entry

    def get_entries(self, event_type: Optional[str] = None) -> List[HistoryEntry]:
        """Retrieves history logs, optionally filtered by event type."""
        with self.wm._lock:
            entries = list(self.wm.get("history_entries") or [])
            if event_type is not None:
                return [e for e in entries if e.event_type == event_type]
            return entries


class WorkingMemory:
    """
    WorkingMemory manager. Provides thread-safe APIs to store, retrieve,
    clear, and restore short-term cognitive states and runtime sessions.
    """
    def __init__(self, history_limit: int = 100) -> None:
        self._lock = threading.RLock()
        self.state = WorkingMemoryState()
        self.context_manager = MemoryContextManager(self)
        self.history_manager = MemoryHistoryManager(self, limit=history_limit)
        
        try:
            from nova.actions.base import BaseAction
            BaseAction._shared_working_memory = self
        except Exception:
            pass
        logger.info("Working memory system initialized.")

    def log_system_event(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> HistoryEntry:
        """Utility wrapper to log generic system events."""
        with self._lock:
            return self.history_manager.add_entry("system_event", message, metadata)

    def set(self, key: str, value: Any) -> None:
        """
        Sets a value in working memory.
        """
        with self._lock:
            if hasattr(self.state.session_state, key):
                orig_val = getattr(self.state.session_state, key)
                try:
                    setattr(self.state.session_state, key, value)
                    self.state.session_state.validate()
                    logger.debug(f"Session state attribute updated: '{key}'", extra={"key": key, "value": value})
                except Exception as e:
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
        with self._lock:
            if hasattr(self.state.session_state, key):
                return getattr(self.state.session_state, key)
            if hasattr(self.state, key) and key != "additional_properties" and key != "session_state":
                return getattr(self.state, key)
            return self.state.additional_properties.get(key, default)

    def remove(self, key: str) -> None:
        with self._lock:
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
        with self._lock:
            self.state = WorkingMemoryState()
            logger.info("Working memory successfully cleared.")

    def snapshot(self) -> Dict[str, Any]:
        logger.info("Creating working memory snapshot.")
        with self._lock:
            return asdict(self.state)

    def restore(self, snapshot_data: Dict[str, Any]) -> None:
        if not isinstance(snapshot_data, dict):
            logger.error("Failed to restore memory snapshot: Invalid format.")
            raise ValueError("Snapshot data must be a dictionary.")

        with self._lock:
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
        with self._lock:
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

            self.history_manager.add_entry("user_interaction", f"User: {user_prompt}", {"intent": intent})
            self.history_manager.add_entry("assistant_response", f"Assistant: {assistant_response}", {"intent": intent})
            logger.info("Appended interaction to conversation history.")

    def reset(self) -> None:
        with self._lock:
            self.clear()
            logger.info("Working memory system reset.")


# ==========================================
# HISTORY MANAGER FROM history.py
# ==========================================

class HistoryManager:
    @staticmethod
    def load_history() -> List[Dict[str, Any]]:
        """Load interaction history from history.json."""
        if not HISTORY_JSON_PATH.exists():
            return []
        try:
            with open(HISTORY_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            log_error("Failed to load history file", e)
            return []

    @staticmethod
    def save_history(history: List[Dict[str, Any]]) -> None:
        """Save interaction history to history.json."""
        try:
            with open(HISTORY_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            log_error("Failed to save history file", e)

    @classmethod
    def add_entry(
        cls,
        user_input: str,
        parsed_action: Dict[str, Any],
        executed_commands: List[str],
        status: str,
        result_message: str = "",
    ) -> None:
        """Add a new history entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "parsed_action": parsed_action,
            "executed_commands": executed_commands,
            "status": status,
            "result_message": result_message,
        }
        history = cls.load_history()
        history.append(entry)
        cls.save_history(history)

    @classmethod
    def print_history(cls, limit: int = 10) -> None:
        """Print recent history entries."""
        from nova.utils import COLOR_BOLD, COLOR_RESET, COLOR_RED, _write
        entries = cls.load_history()
        if not entries:
            _write("No history entries found.\n")
            return

        header = f"{COLOR_BOLD}=== Recent Nova History (last {min(limit, len(entries))} entries) ==={COLOR_RESET}\n"
        _write(header)
        for entry in entries[-limit:]:
            timestamp = entry.get("timestamp", "")
            try:
                ts_formatted = timestamp.split(".")[0].replace("T", " ")
            except Exception:
                ts_formatted = timestamp
            user_input = entry.get("user_input", "")
            status = entry.get("status", "")
            executed_commands = entry.get("executed_commands", [])

            status_color = COLOR_RESET
            if status == "success":
                status_color = "\033[92m"  # Light green
            elif "failed" in status or "error" in status or "exception" in status:
                status_color = COLOR_RED

            _write(f"[{ts_formatted}] {COLOR_BOLD}Input:{COLOR_RESET} {user_input}\n")
            _write(f"  {COLOR_BOLD}Status:{COLOR_RESET} {status_color}{status}{COLOR_RESET}\n")
            if executed_commands:
                _write(f"  {COLOR_BOLD}Commands:{COLOR_RESET} {', '.join(executed_commands)}\n")
            _write("\n")


# ==========================================
# LONG-TERM MEMORY (LTM) SYSTEM FROM long_term_memory.py
# ==========================================

class MemoryCategory:
    USER_PROFILE = "user_profile"
    PREFERENCES = "preferences"
    PROJECTS = "projects"
    DEVICES = "devices"
    GOALS = "goals"
    SKILLS = "skills"
    RELATIONSHIPS = "relationships"
    FACTS = "facts"
    KNOWLEDGE = "knowledge"
    CUSTOM = "custom"

    SYSTEM_CATEGORIES = {
        USER_PROFILE,
        PREFERENCES,
        PROJECTS,
        DEVICES,
        GOALS,
        SKILLS,
        RELATIONSHIPS,
        FACTS,
        KNOWLEDGE,
        CUSTOM
    }


class MemoryClassifier:
    def __init__(self, custom_categories: Optional[List[str]] = None) -> None:
        self._categories = set(MemoryCategory.SYSTEM_CATEGORIES)
        if custom_categories:
            for cat in custom_categories:
                self.register_category(cat)

    def register_category(self, category: str) -> None:
        category_clean = category.strip().lower()
        if not category_clean:
            raise ValueError("Category name cannot be empty.")
        self._categories.add(category_clean)
        logger.info(f"Registered custom memory category: '{category_clean}'")

    def get_registered_categories(self) -> List[str]:
        return sorted(list(self._categories))

    def validate_category(self, category: str) -> bool:
        return category.strip().lower() in self._categories

    def classify_text(self, text: str) -> str:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ("name is", "born in", "live in", "i am a", "my age", "profile")):
            return MemoryCategory.USER_PROFILE
        if any(kw in text_lower for kw in ("like", "dislike", "prefer", "favorite", "hobby", "love to", "loves to")):
            return MemoryCategory.PREFERENCES
        if any(kw in text_lower for kw in ("project", "repo", "codebase", "develop", "build", "task")):
            return MemoryCategory.PROJECTS
        if any(kw in text_lower for kw in ("phone", "computer", "laptop", "device", "server", "hardware")):
            return MemoryCategory.DEVICES
        if any(kw in text_lower for kw in ("want to", "goal", "plan to", "aim", "target", "aspire")):
            return MemoryCategory.GOALS
        if any(kw in text_lower for kw in ("python", "javascript", "program", "fluent in", "know how to", "expert")):
            return MemoryCategory.SKILLS
        if any(kw in text_lower for kw in ("friend", "spouse", "wife", "husband", "son", "daughter", "mother", "father", "colleague", "sister", "brother", "boss", "manager")):
            return MemoryCategory.RELATIONSHIPS
        if any(kw in text_lower for kw in ("did you know", "fact", "definition", "capital of", "sun rises")):
            return MemoryCategory.FACTS
        return MemoryCategory.KNOWLEDGE


@dataclass
class Memory:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = "general"
    title: str = ""
    content: str = ""
    importance: int = 1
    confidence: float = 1.0
    source: str = "user"
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    version: int = 1
    active: bool = True
    meta_notes: str = ""

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Memory ID must be a non-empty string.")
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("Memory category must be a non-empty string.")
        if len(self.category) > 100:
            raise ValueError("Category name cannot exceed 100 characters.")
        if not re.match(r"^[a-zA-Z0-9_]+$", self.category):
            raise ValueError("Category must only contain alphanumeric characters and underscores.")
            
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Memory title must be a non-empty string.")
        if len(self.title) > 500:
            raise ValueError("Memory title cannot exceed 500 characters.")
            
        if not isinstance(self.content, str):
            raise TypeError("Memory content must be a string.")
        if len(self.content) > 1000000:
            raise ValueError("Memory content cannot exceed 1,000,000 characters.")
            
        if not isinstance(self.importance, int) or not (1 <= self.importance <= 5):
            raise ValueError("Memory importance must be an integer between 1 and 5.")
        if not isinstance(self.confidence, (int, float)) or not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Memory confidence must be a float between 0.0 and 1.0.")
            
        if not isinstance(self.tags, list):
            raise TypeError("Memory tags must be a list of strings.")
        if len(self.tags) > 100:
            raise ValueError("Memory tags list cannot exceed 100 items.")
        for tag in self.tags:
            if not isinstance(tag, str):
                raise TypeError("All items in tags must be strings.")

        if not isinstance(self.created_at, (int, float)) or self.created_at <= 0:
            raise ValueError("created_at must be a positive number.")
        if not isinstance(self.updated_at, (int, float)) or self.updated_at <= 0:
            raise ValueError("updated_at must be a positive number.")
        if not isinstance(self.accessed_at, (int, float)) or self.accessed_at <= 0:
            raise ValueError("accessed_at must be a positive number.")
        if not isinstance(self.access_count, int) or self.access_count < 0:
            raise ValueError("access_count must be a non-negative integer.")
        if not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer starting at 1.")
        if not isinstance(self.active, bool):
            raise TypeError("active must be a boolean.")
        if not isinstance(self.meta_notes, str):
            raise TypeError("meta_notes must be a string.")


class BaseMemoryStorage(ABC):
    @abstractmethod
    def save(self, memory: Memory) -> None:
        pass

    @abstractmethod
    def load(self, memory_id: str) -> Optional[Memory]:
        pass

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        pass

    @abstractmethod
    def list_all(self, category: Optional[str] = None, active_only: bool = True) -> List[Memory]:
        pass

    @abstractmethod
    def query_memories(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active_only: bool = True
    ) -> List[Memory]:
        pass

    @abstractmethod
    def get_history_version(self, memory_id: str, version: int) -> Optional[Memory]:
        pass

    @abstractmethod
    def check_integrity(self) -> bool:
        pass

    @abstractmethod
    def backup_database(self, dest_db_path: str) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class SQLiteMemoryStorage(BaseMemoryStorage):
    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._initialize_db()

    def _initialize_db(self) -> None:
        with self._lock:
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.execute("PRAGMA synchronous = NORMAL;")
            self.conn.execute("PRAGMA foreign_keys = ON;")
            self.conn.execute("PRAGMA busy_timeout = 5000;")
            self.conn.execute("PRAGMA cache_size = -2000;")
            self.conn.execute("PRAGMA temp_store = MEMORY;")
            
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                )
            """)
            self.conn.commit()

            cursor = self.conn.cursor()
            cursor.execute("SELECT MAX(version) FROM schema_info")
            row = cursor.fetchone()
            current_version = row[0] if (row and row[0] is not None) else 0

            target_version = 4
            for step in range(current_version + 1, target_version + 1):
                try:
                    logger.info(f"Applying schema migration step {step} for LTM Storage...")
                    self._apply_migration_step(step)
                    logger.info(f"Successfully migrated LTM database to version {step}.")
                except Exception as e:
                    self.conn.rollback()
                    logger.error(f"Failed to apply database migration step {step}: {e}")
                    raise e

    def _apply_migration_step(self, step: int) -> None:
        if step == 1:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    accessed_at REAL NOT NULL,
                    access_count INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    active INTEGER NOT NULL
                )
            """)
        elif step == 2:
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON long_term_memories (category);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_at ON long_term_memories (created_at);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON long_term_memories (importance);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_active ON long_term_memories (active);")
        elif step == 3:
            self.conn.execute("ALTER TABLE long_term_memories ADD COLUMN meta_notes TEXT DEFAULT ''")
        elif step == 4:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memory_history (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    meta_notes TEXT NOT NULL,
                    FOREIGN KEY (memory_id) REFERENCES long_term_memories (id) ON DELETE CASCADE
                )
            """)
            self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_history_mem_version ON long_term_memory_history (memory_id, version);")
            
        self.conn.execute("INSERT INTO schema_info (version, applied_at) VALUES (?, ?)", (step, time.time()))
        self.conn.commit()

    def _row_to_memory(self, row: tuple) -> Memory:
        meta_notes = row[14] if len(row) > 14 else ""
        return Memory(
            id=row[0],
            category=row[1],
            title=row[2],
            content=row[3],
            importance=row[4],
            confidence=row[5],
            source=row[6],
            tags=json.loads(row[7]),
            created_at=row[8],
            updated_at=row[9],
            accessed_at=row[10],
            access_count=row[11],
            version=row[12],
            active=bool(row[13]),
            meta_notes=meta_notes
        )

    def save(self, memory: Memory) -> None:
        memory.validate()
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM long_term_memories WHERE id = ?", (memory.id,))
            row = cursor.fetchone()
            
            try:
                if row:
                    old_mem = self._row_to_memory(row)
                    if old_mem.version < memory.version:
                        history_id = str(uuid.uuid4())
                        self.conn.execute("""
                            INSERT OR REPLACE INTO long_term_memory_history (
                                id, memory_id, version, category, title, content, importance, confidence,
                                source, tags, updated_at, meta_notes
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            history_id,
                            old_mem.id,
                            old_mem.version,
                            old_mem.category,
                            old_mem.title,
                            old_mem.content,
                            old_mem.importance,
                            old_mem.confidence,
                            old_mem.source,
                            json.dumps(old_mem.tags),
                            old_mem.updated_at,
                            old_mem.meta_notes
                        ))

                    cursor.execute("PRAGMA table_info(long_term_memories)")
                    columns = [col[1] for col in cursor.fetchall()]

                    if "meta_notes" in columns:
                        self.conn.execute("""
                            UPDATE long_term_memories SET
                                category = ?, title = ?, content = ?, importance = ?, confidence = ?,
                                source = ?, tags = ?, created_at = ?, updated_at = ?, accessed_at = ?,
                                access_count = ?, version = ?, active = ?, meta_notes = ?
                            WHERE id = ?
                        """, (
                            memory.category,
                            memory.title,
                            memory.content,
                            memory.importance,
                            memory.confidence,
                            memory.source,
                            json.dumps(memory.tags),
                            memory.created_at,
                            memory.updated_at,
                            memory.accessed_at,
                            memory.access_count,
                            memory.version,
                            int(memory.active),
                            memory.meta_notes,
                            memory.id
                        ))
                    else:
                        self.conn.execute("""
                            UPDATE long_term_memories SET
                                category = ?, title = ?, content = ?, importance = ?, confidence = ?,
                                source = ?, tags = ?, created_at = ?, updated_at = ?, accessed_at = ?,
                                access_count = ?, version = ?, active = ?
                            WHERE id = ?
                        """, (
                            memory.category,
                            memory.title,
                            memory.content,
                            memory.importance,
                            memory.confidence,
                            memory.source,
                            json.dumps(memory.tags),
                            memory.created_at,
                            memory.updated_at,
                            memory.accessed_at,
                            memory.access_count,
                            memory.version,
                            int(memory.active),
                            memory.id
                        ))
                else:
                    cursor.execute("PRAGMA table_info(long_term_memories)")
                    columns = [col[1] for col in cursor.fetchall()]

                    if "meta_notes" in columns:
                        self.conn.execute("""
                            INSERT INTO long_term_memories (
                                id, category, title, content, importance, confidence, source, tags,
                                created_at, updated_at, accessed_at, access_count, version, active, meta_notes
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            memory.id,
                            memory.category,
                            memory.title,
                            memory.content,
                            memory.importance,
                            memory.confidence,
                            memory.source,
                            json.dumps(memory.tags),
                            memory.created_at,
                            memory.updated_at,
                            memory.accessed_at,
                            memory.access_count,
                            memory.version,
                            int(memory.active),
                            memory.meta_notes
                        ))
                    else:
                        self.conn.execute("""
                            INSERT INTO long_term_memories (
                                id, category, title, content, importance, confidence, source, tags,
                                created_at, updated_at, accessed_at, access_count, version, active
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            memory.id,
                            memory.category,
                            memory.title,
                            memory.content,
                            memory.importance,
                            memory.confidence,
                            memory.source,
                            json.dumps(memory.tags),
                            memory.created_at,
                            memory.updated_at,
                            memory.accessed_at,
                            memory.access_count,
                            memory.version,
                            int(memory.active)
                        ))
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Transaction rolled back. Failed to save LTM: {e}")
                raise e

    def load(self, memory_id: str) -> Optional[Memory]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM long_term_memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_memory(row)
        return None

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute("DELETE FROM long_term_memories WHERE id = ?", (memory_id,))
                self.conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Transaction rolled back. Failed to delete memory '{memory_id}': {e}")
                raise e

    def list_all(self, category: Optional[str] = None, active_only: bool = True) -> List[Memory]:
        return self.query_memories(category=category, active_only=active_only)

    def query_memories(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active_only: bool = True
    ) -> List[Memory]:
        query = "SELECT * FROM long_term_memories WHERE 1=1"
        params: List[Any] = []

        if category is not None:
            query += " AND category = ?"
            params.append(category)

        if active_only:
            query += " AND active = 1"

        if title is not None:
            query += " AND title LIKE ?"
            params.append(f"%{title}%")

        if tags is not None:
            for tag in tags:
                query += " AND tags LIKE ?"
                params.append(f'%"{tag}"%')

        if keywords is not None:
            for kw in keywords:
                query += " AND (title LIKE ? OR content LIKE ?)"
                params.extend([f"%{kw}%", f"%{kw}%"])

        if metadata is not None:
            for key, val in metadata.items():
                if key in ("importance", "confidence", "source", "version", "access_count"):
                    query += f" AND {key} = ?"
                    params.append(val)

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
        memories = []
        for row in rows:
            try:
                memories.append(self._row_to_memory(row))
            except Exception as e:
                logger.error(f"Failed to parse query memory row: {e}")
        return memories

    def get_history_version(self, memory_id: str, version: int) -> Optional[Memory]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM long_term_memory_history 
                WHERE memory_id = ? AND version = ?
            """, (memory_id, version))
            row = cursor.fetchone()
            if row:
                cursor.execute("SELECT created_at, accessed_at, access_count, active FROM long_term_memories WHERE id = ?", (memory_id,))
                orig = cursor.fetchone()
                created_at = orig[0] if orig else row[10]
                accessed_at = orig[1] if orig else row[10]
                access_count = orig[2] if orig else 0
                active = bool(orig[3]) if orig else True
                
                return Memory(
                    id=row[1],
                    category=row[3],
                    title=row[4],
                    content=row[5],
                    importance=row[6],
                    confidence=row[7],
                    source=row[8],
                    tags=json.loads(row[9]),
                    created_at=created_at,
                    updated_at=row[10],
                    accessed_at=accessed_at,
                    access_count=access_count,
                    version=row[2],
                    active=active,
                    meta_notes=row[11]
                )
        return None

    def check_integrity(self) -> bool:
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                row = cursor.fetchone()
                return bool(row and row[0] == "ok")
            except Exception as e:
                logger.error(f"LTM database integrity check failed: {e}")
                return False

    def backup_database(self, dest_db_path: str) -> None:
        with self._lock:
            dst = sqlite3.connect(dest_db_path)
            try:
                self.conn.backup(dst)
                logger.info(f"LTM database backed up successfully to: {dest_db_path}")
            except Exception as e:
                logger.error(f"LTM database backup failed: {e}")
                raise e
            finally:
                dst.close()

    def close(self) -> None:
        with self._lock:
            self.conn.close()
        logger.info("SQLite connection closed.")


class BaseSemanticRetriever(ABC):
    @abstractmethod
    def retrieve_semantic(self, query: str, limit: int = 5) -> List[Memory]:
        pass


class BaseMemoryRanker(ABC):
    @abstractmethod
    def rank(self, memories: List[Memory]) -> List[Memory]:
        pass


class HeuristicMemoryRanker(BaseMemoryRanker):
    def __init__(self, weights: Optional[Dict[str, float]] = None, category_priorities: Optional[Dict[str, float]] = None, decay_half_life: float = 86400.0) -> None:
        self.weights = weights or {
            "importance": 0.3,
            "confidence": 0.2,
            "recency": 0.2,
            "frequency": 0.1,
            "category": 0.2
        }
        self.category_priorities = category_priorities or {
            "user_profile": 1.5,
            "preferences": 1.3,
            "goals": 1.2,
            "relationships": 1.2,
            "skills": 1.1,
            "projects": 1.0,
            "devices": 1.0,
            "facts": 1.0,
            "knowledge": 0.8
        }
        self.decay_half_life = decay_half_life

    def calculate_score(self, memory: Memory, now: float) -> float:
        s_imp = memory.importance / 5.0
        s_conf = memory.confidence
        
        delta_t = max(0.0, now - memory.updated_at)
        decay_constant = 0.69314718 / self.decay_half_life
        s_rec = math.exp(-decay_constant * delta_t)
        
        s_freq = memory.access_count / (memory.access_count + 1.0)
        s_cat = self.category_priorities.get(memory.category.lower(), 1.0)
        
        score = (
            self.weights["importance"] * s_imp +
            self.weights["confidence"] * s_conf +
            self.weights["recency"] * s_rec +
            self.weights["frequency"] * s_freq +
            self.weights["category"] * s_cat
        )
        return score

    def rank(self, memories: List[Memory]) -> List[Memory]:
        now = time.time()
        return sorted(memories, key=lambda m: self.calculate_score(m, now), reverse=True)


class MemoryRetriever:
    def __init__(self, storage: BaseMemoryStorage, semantic_backend: Optional[BaseSemanticRetriever] = None, ranker: Optional[BaseMemoryRanker] = None) -> None:
        self.storage = storage
        self.semantic_backend = semantic_backend
        self.ranker = ranker or HeuristicMemoryRanker()
        logger.info("Memory Retriever initialized.")

    def retrieve(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active_only: bool = True,
        use_semantic: bool = True
    ) -> List[Memory]:
        results = []
        if query and use_semantic and self.semantic_backend:
            try:
                logger.info(f"Executing semantic retrieval for query: '{query}'")
                semantic_results = self.semantic_backend.retrieve_semantic(query)
                for mem in semantic_results:
                    if active_only and not mem.active:
                        continue
                    if category and mem.category != category:
                        continue
                    if tags and not all(t in mem.tags for t in tags):
                        continue
                    if title and title.lower() not in mem.title.lower():
                        continue
                    if metadata:
                        match = True
                        for k, v in metadata.items():
                            if getattr(mem, k, None) != v:
                                match = False
                                break
                        if not match:
                            continue
                    results.append(mem)
            except Exception as e:
                logger.error(f"Semantic search failed: {e}. Falling back to standard query.")
                results = self.storage.query_memories(
                    category=category,
                    tags=tags,
                    keywords=keywords,
                    title=title,
                    metadata=metadata,
                    active_only=active_only
                )
        else:
            results = self.storage.query_memories(
                category=category,
                tags=tags,
                keywords=keywords,
                title=title,
                metadata=metadata,
                active_only=active_only
            )

        return self.ranker.rank(results)


class LongTermMemoryManager:
    def __init__(self, storage: BaseMemoryStorage, classifier: Optional[MemoryClassifier] = None, retriever: Optional[MemoryRetriever] = None) -> None:
        self.storage = storage
        self.classifier = classifier or MemoryClassifier()
        self.retriever = retriever or MemoryRetriever(self.storage)
        logger.info("Long-Term Memory Manager initialized.")

    def check_integrity(self) -> bool:
        return self.storage.check_integrity()

    def backup_database(self, dest_db_path: str) -> None:
        self.storage.backup_database(dest_db_path)

    def create_memory(
        self,
        category: str,
        title: str,
        content: str,
        importance: int = 1,
        confidence: float = 1.0,
        source: str = "user",
        tags: Optional[List[str]] = None,
        meta_notes: str = ""
    ) -> Memory:
        category_clean = category.strip().lower()
        if not self.classifier.validate_category(category_clean):
            raise ValueError(f"Category '{category}' is not a registered category.")

        existing = self.retriever.retrieve(category=category_clean, title=title, active_only=True)
        exact_match = [m for m in existing if m.title.lower() == title.strip().lower()]
        
        if exact_match:
            dup = exact_match[0]
            logger.info(f"Duplicate LTM detected. Merging values into memory '{dup.id}'.")
            merged_tags = list(set(dup.tags + (tags or [])))
            notes = f"Merged from duplicate. {meta_notes}".strip()
            return self.update_memory(
                dup.id,
                content=content,
                importance=max(dup.importance, importance),
                confidence=max(dup.confidence, confidence),
                tags=merged_tags,
                meta_notes=notes
            )

        now = time.time()
        memory = Memory(
            category=category_clean,
            title=title.strip(),
            content=content,
            importance=importance,
            confidence=confidence,
            source=source,
            tags=tags or [],
            created_at=now,
            updated_at=now,
            accessed_at=now,
            access_count=0,
            version=1,
            active=True,
            meta_notes=meta_notes
        )
        self.storage.save(memory)
        logger.info(f"Created new memory: [{category_clean}] '{title}' (ID: {memory.id})")
        return memory

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        memory = self.storage.load(memory_id)
        if memory:
            memory.accessed_at = time.time()
            memory.access_count += 1
            self.storage.save(memory)
            logger.debug(f"Retrieved memory '{memory_id}' (Access count: {memory.access_count})")
        return memory

    def update_memory(self, memory_id: str, **kwargs) -> Memory:
        memory = self.storage.load(memory_id)
        if not memory:
            logger.error(f"Cannot update memory: ID '{memory_id}' not found.")
            raise ValueError(f"Memory with ID '{memory_id}' does not exist.")

        if "category" in kwargs:
            category_clean = kwargs["category"].strip().lower()
            if not self.classifier.validate_category(category_clean):
                raise ValueError(f"Category '{kwargs['category']}' is not a registered category.")
            kwargs["category"] = category_clean

        read_only = {"id", "created_at", "accessed_at", "access_count", "version"}
        for key, value in kwargs.items():
            if key in read_only:
                continue
            if hasattr(memory, key):
                setattr(memory, key, value)

        memory.updated_at = time.time()
        memory.version += 1
        memory.validate()
        
        self.storage.save(memory)
        logger.info(f"Updated memory '{memory_id}' to version {memory.version}.")
        return memory

    def delete_memory(self, memory_id: str) -> bool:
        success = self.storage.delete(memory_id)
        if success:
            logger.info(f"Deleted memory '{memory_id}' successfully.")
        else:
            logger.warning(f"Attempted to delete non-existent memory '{memory_id}'.")
        return success

    def rollback_memory(self, memory_id: str, target_version: int) -> Memory:
        historical = self.storage.get_history_version(memory_id, target_version)
        if not historical:
            raise ValueError(f"Historical version {target_version} for memory '{memory_id}' not found.")
            
        current = self.storage.load(memory_id)
        if not current:
            raise ValueError(f"Memory with ID '{memory_id}' not found in DB.")

        current.category = historical.category
        current.title = historical.title
        current.content = historical.content
        current.importance = historical.importance
        current.confidence = historical.confidence
        current.source = historical.source
        current.tags = historical.tags
        current.meta_notes = f"Rolled back to version {target_version}. Previous version was {current.version}."
        
        current.updated_at = time.time()
        current.version += 1
        current.validate()
        
        self.storage.save(current)
        logger.info(f"Memory '{memory_id}' rolled back to version {target_version} (new version is {current.version}).")
        return current

    def list_memories(self, category: Optional[str] = None, active_only: bool = True) -> List[Memory]:
        category_clean = category.strip().lower() if category is not None else None
        return self.storage.list_all(category=category_clean, active_only=active_only)

    def import_memories(self, data: List[Dict[str, Any]]) -> int:
        imported_count = 0
        for item in data:
            try:
                tags = item.get("tags", [])
                if isinstance(tags, str):
                    tags = json.loads(tags)

                category_clean = item.get("category", "general").strip().lower()
                if not self.classifier.validate_category(category_clean):
                    self.classifier.register_category(category_clean)

                mem = Memory(
                    id=item.get("id", str(uuid.uuid4())),
                    category=category_clean,
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    importance=item.get("importance", 1),
                    confidence=item.get("confidence", 1.0),
                    source=item.get("source", "user"),
                    tags=tags,
                    created_at=item.get("created_at", time.time()),
                    updated_at=item.get("updated_at", time.time()),
                    accessed_at=item.get("accessed_at", time.time()),
                    access_count=item.get("access_count", 0),
                    version=item.get("version", 1),
                    active=bool(item.get("active", True)),
                    meta_notes=item.get("meta_notes", "")
                )
                self.storage.save(mem)
                imported_count += 1
            except Exception as e:
                logger.error(f"Failed to import memory entry: {e}")
                
        logger.info(f"Imported {imported_count} memories successfully.")
        return imported_count

    def export_memories(self) -> List[Dict[str, Any]]:
        memories = self.storage.list_all(active_only=False)
        exported = [asdict(m) for m in memories]
        logger.info(f"Exported {len(exported)} memories.")
        return exported


@dataclass
class ConsolidationProposal:
    action: str
    primary_id: str
    target_ids: List[str]
    reason: str
    proposed_state: Dict[str, Any] = field(default_factory=dict)


class MemoryConsolidator:
    def __init__(self, manager: LongTermMemoryManager, inactive_seconds: float = 2592000) -> None:
        self.manager = manager
        self.inactive_seconds = inactive_seconds

    def _get_words(self, text: str) -> set[str]:
        return set(w.strip(".,!?;:()[]\"'") for w in text.lower().split() if len(w) > 2)

    def _jaccard_similarity(self, s1: set[str], s2: set[str]) -> float:
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)

    def compress_all_metadata(self) -> int:
        all_memories = self.manager.list_memories(active_only=False)
        compressed_count = 0
        for mem in all_memories:
            modified = False
            cleaned_tags = sorted(list(set(t.strip().lower() for t in mem.tags if t.strip())))
            if cleaned_tags != mem.tags:
                mem.tags = cleaned_tags
                modified = True
            cleaned_title = mem.title.strip()
            if cleaned_title != mem.title:
                mem.title = cleaned_title
                modified = True
            cleaned_content = mem.content.strip()
            if cleaned_content != mem.content:
                mem.content = cleaned_content
                modified = True
            if modified:
                mem.validate()
                self.manager.storage.save(mem)
                compressed_count += 1
        if compressed_count > 0:
            logger.info(f"Compressed redundant metadata for {compressed_count} memories.")
        return compressed_count

    def prepare_consolidation(self) -> List[ConsolidationProposal]:
        self.compress_all_metadata()
        all_memories = self.manager.list_memories(active_only=True)
        proposals: List[ConsolidationProposal] = []
        processed_ids = set()
        now = time.time()

        by_category: Dict[str, List[Memory]] = {}
        for mem in all_memories:
            by_category.setdefault(mem.category, []).append(mem)

        for category, memories in by_category.items():
            n = len(memories)
            for i in range(n):
                m1 = memories[i]
                if m1.id in processed_ids:
                    continue
                for j in range(i + 1, n):
                    m2 = memories[j]
                    if m2.id in processed_ids:
                        continue

                    t1_words = self._get_words(m1.title)
                    t2_words = self._get_words(m2.title)
                    title_sim = self._jaccard_similarity(t1_words, t2_words)

                    c1_words = self._get_words(m1.content)
                    c2_words = self._get_words(m2.content)
                    content_sim = self._jaccard_similarity(c1_words, c2_words)

                    if title_sim > 0.4 and category in (MemoryCategory.PREFERENCES, MemoryCategory.FACTS):
                        if m1.updated_at < m2.updated_at:
                            old, new = m1, m2
                        else:
                            old, new = m2, m1
                        if old.importance == 5:
                            continue
                        proposal = ConsolidationProposal(
                            action="delete_obsolete",
                            primary_id=new.id,
                            target_ids=[old.id],
                            reason=f"Stale preference/fact override. '{new.title}' (updated {new.updated_at}) supersedes '{old.title}' (updated {old.updated_at})."
                        )
                        proposals.append(proposal)
                        processed_ids.add(old.id)
                        break
                    elif content_sim > 0.5 or (title_sim > 0.5 and content_sim > 0.3):
                        if m1.created_at <= m2.created_at:
                            primary, target = m1, m2
                        else:
                            primary, target = m2, m1
                        merged_tags = sorted(list(set(primary.tags + target.tags)))
                        merged_content = f"{primary.content}\n{target.content}".strip()
                        proposal = ConsolidationProposal(
                            action="merge",
                            primary_id=primary.id,
                            target_ids=[target.id],
                            reason=f"Semantic duplicate in '{category}'. Content overlap: {content_sim:.2f}, Title overlap: {title_sim:.2f}.",
                            proposed_state={
                                "content": merged_content,
                                "tags": merged_tags,
                                "importance": max(primary.importance, target.importance),
                                "confidence": max(primary.confidence, target.confidence),
                                "meta_notes": f"Consolidated content from duplicate memory {target.id}."
                            }
                        )
                        proposals.append(proposal)
                        processed_ids.add(target.id)
                        processed_ids.add(primary.id)
                        break

        for mem in all_memories:
            if mem.id in processed_ids:
                continue
            time_stale = now - max(mem.created_at, mem.updated_at)
            if mem.access_count == 0 and time_stale > self.inactive_seconds:
                if mem.importance == 5:
                    continue
                proposal = ConsolidationProposal(
                    action="archive",
                    primary_id=mem.id,
                    target_ids=[],
                    reason=f"Memory has not been accessed and is older than {self.inactive_seconds / 86400:.1f} days."
                )
                proposals.append(proposal)
                processed_ids.add(mem.id)

        return proposals

    def apply_consolidation(self, proposals: List[ConsolidationProposal]) -> int:
        applied_count = 0
        for prop in proposals:
            try:
                if prop.action == "merge":
                    self.manager.update_memory(prop.primary_id, **prop.proposed_state)
                    for target_id in prop.target_ids:
                        self.manager.update_memory(target_id, active=False, meta_notes=f"Merged into memory {prop.primary_id}.")
                    applied_count += 1
                    logger.info(f"Applied merge: {prop.primary_id} <- {prop.target_ids}")
                elif prop.action == "delete_obsolete":
                    for target_id in prop.target_ids:
                        self.manager.delete_memory(target_id)
                    applied_count += 1
                    logger.info(f"Applied obsolete deletion on targets: {prop.target_ids}")
                elif prop.action == "archive":
                    self.manager.update_memory(prop.primary_id, active=False, meta_notes="Archived due to inactivity.")
                    applied_count += 1
                    logger.info(f"Applied archival: {prop.primary_id}")
            except Exception as e:
                logger.error(f"Failed to apply consolidation proposal: {e}")
        return applied_count


class BasePromotionRule(ABC):
    @abstractmethod
    def evaluate(self, text: str) -> Optional[Dict[str, Any]]:
        pass


class PreferencePromotionRule(BasePromotionRule):
    def evaluate(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ("i prefer", "my favorite", "always use", "dislike", "i like to", "favorite editor", "prefer using")):
            return {
                "category": MemoryCategory.PREFERENCES,
                "title": f"Preference: {text[:30].strip()}...",
                "content": text.strip(),
                "importance": 3,
                "confidence": 0.9,
                "tags": ["preferences", "promoted"]
            }
        return None


class GoalPromotionRule(BasePromotionRule):
    def evaluate(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ("my goal is", "i want to learn", "plan to build", "aim to", "target to", "long-term plan")):
            return {
                "category": MemoryCategory.GOALS,
                "title": f"Goal: {text[:30].strip()}...",
                "content": text.strip(),
                "importance": 4,
                "confidence": 0.95,
                "tags": ["goals", "promoted"]
            }
        return None


class UserProfilePromotionRule(BasePromotionRule):
    def evaluate(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ("my name is", "i live in", "i work as", "i am a", "born in")):
            return {
                "category": MemoryCategory.USER_PROFILE,
                "title": f"Profile: {text[:30].strip()}...",
                "content": text.strip(),
                "importance": 4,
                "confidence": 1.0,
                "tags": ["user_profile", "promoted"]
            }
        return None


class ProjectPromotionRule(BasePromotionRule):
    def evaluate(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ("project", "repository", "building a", "developing", "codebase", "github.com/")):
            return {
                "category": MemoryCategory.PROJECTS,
                "title": f"Project: {text[:30].strip()}...",
                "content": text.strip(),
                "importance": 3,
                "confidence": 0.9,
                "tags": ["projects", "promoted"]
            }
        return None


class ExclusionFilter:
    def is_excluded(self, text: str) -> bool:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ("volume up", "volume down", "mute", "unmute", "set volume", "sound level")):
            return True
        if any(kw in text_lower for kw in ("http://", "https://", "chrome://", "open tab", "active tab", "browser tab", "localhost:")):
            return True
        if any(kw in text_lower for kw in ("ls", "cd ", "pwd", "clear", "mkdir", "rm -rf", "git status", "git diff")):
            if len(text.strip().split()) <= 4:
                return True
        return False


class MemoryPromoter:
    def __init__(
        self,
        ltm_manager: LongTermMemoryManager,
        rules: Optional[List[BasePromotionRule]] = None,
        exclusion_filter: Optional[ExclusionFilter] = None
    ) -> None:
        self.ltm_manager = ltm_manager
        self.rules = rules or [
            PreferencePromotionRule(),
            GoalPromotionRule(),
            UserProfilePromotionRule(),
            ProjectPromotionRule()
        ]
        self.exclusion_filter = exclusion_filter or ExclusionFilter()

    def promote(self, wm: Any) -> int:
        promoted_count = 0
        candidates = []
        
        conv_history = wm.get("conversation_history") or []
        for inter in conv_history:
            candidates.append((inter.user_prompt, inter.timestamp))
            candidates.append((inter.assistant_response, inter.timestamp))
            
        active_task = wm.get("active_task")
        if active_task:
            candidates.append((f"Active task: {active_task}", time.time()))
        active_goal = wm.get("active_goal")
        if active_goal:
            candidates.append((f"Active goal: {active_goal}", time.time()))
            
        for text, timestamp in candidates:
            if not text or not text.strip():
                continue
            if self.exclusion_filter.is_excluded(text):
                continue
            for rule in self.rules:
                res = rule.evaluate(text)
                if res:
                    try:
                        self.ltm_manager.create_memory(
                            category=res["category"],
                            title=res["title"],
                            content=res["content"],
                            importance=res.get("importance", 2),
                            confidence=res.get("confidence", 0.9),
                            tags=res.get("tags", []),
                            meta_notes=f"Promoted from Working Memory context. Source timestamp: {timestamp}."
                        )
                        promoted_count += 1
                        break
                    except Exception as e:
                        logger.error(f"Failed to promote Working Memory segment to LTM: {e}")
                        
        return promoted_count
