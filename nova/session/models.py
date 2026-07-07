"""
nova.session.models
~~~~~~~~~~~~~~~~~~~
Data models for the Development Session Manager.

Defines:
  - FollowupIntent    : resolved follow-up intent enum
  - TaskRecord        : immutable history entry for a completed task
  - UndoEntry         : lightweight undo/redo stack entry
  - DevelopmentSession: the live session state object
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set


# ── Follow-up Intent ─────────────────────────────────────────────────────────

class FollowupIntent(str, Enum):
    """Resolved intent for a user's natural-language follow-up request."""
    NONE      = "none"       # not a follow-up — pass to normal planning
    CONTINUE  = "continue"   # resume or extend the last task
    UNDO      = "undo"       # undo the most recently completed task
    REDO      = "redo"       # redo the most recently undone task
    EXPLAIN   = "explain"    # explain what was just done
    IMPROVE   = "improve"    # improve the generated code
    REFACTOR  = "refactor"   # refactor the generated code
    ADD_TESTS = "add_tests"  # generate unit tests for changed files
    OPTIMIZE  = "optimize"   # performance-optimize the generated code
    DOCUMENT  = "document"   # add docstrings / docs to changed files


# ── Task Record ───────────────────────────────────────────────────────────────

@dataclass
class TaskRecord:
    """
    Immutable snapshot of a completed (or failed) task kept in session history.
    """
    task_id: str
    goal: str
    status: str                                # "completed" | "failed" | "cancelled"
    steps_executed: int = 0
    steps_completed: int = 0
    steps_failed: int = 0
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    rollbacks: List[str] = field(default_factory=list)
    validation_passed: bool = True
    duration_s: float = 0.0
    finished_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Undo / Redo Entry ─────────────────────────────────────────────────────────

@dataclass
class UndoEntry:
    """
    Lightweight entry stored on the undo/redo stack.

    Stores the CodeEditor history checkpoint length at the moment the task
    started, so the session manager can roll back exactly the edits that
    belong to that task.
    """
    task_id: str
    task_goal: str
    # Length of CodeEditor.history immediately BEFORE the task was executed.
    # Rollback pops history items until this length is reached.
    editor_checkpoint_len: int
    files_affected: List[str] = field(default_factory=list)   # created + modified + deleted
    timestamp: float = field(default_factory=time.time)


# ── Development Session ───────────────────────────────────────────────────────

@dataclass
class DevelopmentSession:
    """
    Live session state object.  A single instance is maintained by
    DevelopmentSessionManager for the lifetime of the Nova process.
    """
    # Identity
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    # Project metadata (populated from ProjectAwarenessEngine)
    project_name: str = ""
    project_root: Optional[Path] = None
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    git_branch: str = ""

    # AI provider
    ai_provider: str = "chatgpt"

    # Active task tracking
    current_task_id: Optional[str] = None
    current_task_goal: Optional[str] = None

    # File change accounting (accumulated across all tasks)
    files_created: Set[str] = field(default_factory=set)
    files_modified: Set[str] = field(default_factory=set)
    files_deleted: Set[str] = field(default_factory=set)

    # History
    task_history: List[TaskRecord] = field(default_factory=list)

    # Conversation rolling window (last 10 turns)
    recent_prompts: Deque[str] = field(
        default_factory=lambda: deque(maxlen=10)
    )
    recent_responses: Deque[str] = field(
        default_factory=lambda: deque(maxlen=10)
    )

    # Undo / redo stacks
    undo_stack: List[UndoEntry] = field(default_factory=list)
    redo_stack: List[UndoEntry] = field(default_factory=list)

    # Arbitrary extension metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── Convenience properties ────────────────────────────────────

    @property
    def last_task_record(self) -> Optional[TaskRecord]:
        """Most recently completed task record, or None."""
        return self.task_history[-1] if self.task_history else None

    @property
    def all_changed_files(self) -> List[str]:
        """Union of created, modified, and deleted files (no duplicates)."""
        return sorted(
            (self.files_created | self.files_modified | self.files_deleted)
        )

    @property
    def duration_s(self) -> float:
        """Elapsed session time in seconds."""
        end = self.ended_at or time.time()
        return round(end - self.started_at, 3)

    @property
    def tasks_completed(self) -> int:
        return sum(1 for r in self.task_history if r.status == "completed")

    @property
    def tasks_failed(self) -> int:
        return sum(1 for r in self.task_history if r.status == "failed")
