from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List, TYPE_CHECKING

from nova.logger import logger

if TYPE_CHECKING:
    from nova.core.memory import WorkingMemory, MemoryContext


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
class MemoryContext:
    """
    Represents a specific runtime focus or workspace context.
    """
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


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
    Coordinates entering, exiting, switching, and restoring cognitive context scopes with thread safety.
    """
    def __init__(self, wm: WorkingMemory):
        self.wm = wm

    @property
    def current_context(self) -> Optional[MemoryContext]:
        with self.wm._lock:
            if self.wm.state.active_contexts:
                return self.wm.state.active_contexts[-1]
            return None

    @property
    def previous_context(self) -> Optional[MemoryContext]:
        with self.wm._lock:
            return self.wm.state.previous_context

    @previous_context.setter
    def previous_context(self, val: Optional[MemoryContext]) -> None:
        with self.wm._lock:
            self.wm.state.previous_context = val

    def enter_context(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> MemoryContext:
        """Pushes a new context onto the stack, making it active."""
        with self.wm._lock:
            ctx = MemoryContext(name=name, metadata=metadata or {})
            self.wm.state.active_contexts.append(ctx)
            logger.info(f"Entered context: '{name}'")
            return ctx

    def exit_context(self, name: Optional[str] = None) -> Optional[MemoryContext]:
        """Pops the active context from the stack and sets it as the previous context."""
        with self.wm._lock:
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
        with self.wm._lock:
            if self.wm.state.active_contexts:
                self.previous_context = self.wm.state.active_contexts.pop()
            ctx = MemoryContext(name=name, metadata=metadata or {})
            self.wm.state.active_contexts.append(ctx)
            logger.info(f"Switched context to: '{name}'")
            return ctx

    def clear_contexts(self) -> None:
        """Wipes the context stack and previous context history."""
        with self.wm._lock:
            self.wm.state.active_contexts.clear()
            self.previous_context = None
            logger.info("Cleared all contexts.")

    def restore_context(self) -> Optional[MemoryContext]:
        """Pushes the previous context back onto the stack."""
        with self.wm._lock:
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
