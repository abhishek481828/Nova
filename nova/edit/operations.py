"""
nova.edit.operations
~~~~~~~~~~~~~~~~~~~~
Data structures for recording, tracking, and rolling back edits.

EditOperation   — immutable record of one edit (before + after content).
EditHistory     — thread-safe FIFO ring-buffer of recent operations.
EditResult      — return value for every CodeEditor public method.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Deque, Dict, Optional


class EditKind(str, Enum):
    """Category of a single edit operation."""
    CREATE         = "create"
    UPDATE         = "update"
    DELETE         = "delete"
    RENAME_FILE    = "rename_file"
    MOVE_FILE      = "move_file"
    RENAME_SYMBOL  = "rename_symbol"
    INSERT_CODE    = "insert_code"
    REPLACE_FUNC   = "replace_function"
    INSERT_IMPORT  = "insert_import"
    REMOVE_FUNC    = "remove_function"
    ROLLBACK       = "rollback"


@dataclass(frozen=True)
class EditOperation:
    """
    Immutable record of a single completed edit.

    Stored in EditHistory for rollback. `old_content` is None for
    CREATE operations; `new_content` is None for DELETE operations.
    """
    kind:         EditKind
    rel_path:     str              # relative to project root
    timestamp:    float = field(default_factory=time.time)
    old_content:  Optional[str] = None   # file content before the edit
    new_content:  Optional[str] = None   # file content after the edit
    # For file rename/move: the destination relative path
    dest_rel_path: Optional[str] = None
    # Extra metadata (symbol old/new name, etc.)
    metadata:     Dict[str, Any] = field(default_factory=dict)

    @property
    def is_reversible(self) -> bool:
        """True if this operation can be rolled back."""
        return self.old_content is not None


@dataclass
class EditResult:
    """
    Returned by every CodeEditor public method.

    Always check `success` before using other fields.
    """
    success:      bool
    message:      str          = ""
    diff:         str          = ""   # unified diff text
    backup_path:  Optional[str] = None
    duration_s:   float        = 0.0
    metadata:     Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "OK", **kwargs) -> "EditResult":
        return cls(success=True, message=message, **kwargs)

    @classmethod
    def fail(cls, message: str, **kwargs) -> "EditResult":
        return cls(success=False, message=message, **kwargs)


class EditHistory:
    """
    Thread-safe ring-buffer of recent EditOperation objects.
    Used to support rollback of the most recent change.

    Parameters
    ----------
    maxlen : int
        Maximum number of operations to keep (default 50).
        Oldest entries are silently dropped when the buffer is full.
    """

    def __init__(self, maxlen: int = 50) -> None:
        self._buf: Deque[EditOperation] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, op: EditOperation) -> None:
        """Add an operation to the history."""
        with self._lock:
            self._buf.append(op)

    def pop_last(self) -> Optional[EditOperation]:
        """
        Remove and return the most recent operation, or None if empty.
        Returns only reversible operations (those with old_content).
        """
        with self._lock:
            while self._buf:
                op = self._buf.pop()
                if op.is_reversible:
                    return op
            return None

    def peek_last(self) -> Optional[EditOperation]:
        """Return the most recent operation without removing it."""
        with self._lock:
            if self._buf:
                return self._buf[-1]
            return None

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    def all_operations(self) -> list:
        """Return a copy of all stored operations (oldest first)."""
        with self._lock:
            return list(self._buf)
