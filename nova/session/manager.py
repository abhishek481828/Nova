"""
nova.session.manager
~~~~~~~~~~~~~~~~~~~~~
DevelopmentSessionManager — the singleton that maintains a persistent
software development session across user requests.

Responsibilities
----------------
* Start / end a session tied to the active project.
* Record tasks as they execute (start, step, complete/fail).
* Accumulate file change sets (created, modified, deleted) per session.
* Maintain a rolling prompt/response window for context injection.
* Provide follow-up intent resolution + goal synthesis.
* Undo / redo the last task using CodeEditor's rollback API.
* Build a compact context prompt string for injection into AI calls.
* Mirror key fields into WorkingMemory.session_state for backward compat.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from nova.session.models import (
    DevelopmentSession,
    FollowupIntent,
    TaskRecord,
    UndoEntry,
)
from nova.session.intent_resolver import resolve_intent

logger = logging.getLogger("nova.session.manager")

# Maximum context lines injected into AI prompts
_MAX_RECENT_PROMPTS_IN_CONTEXT = 2


class DevelopmentSessionManager:
    """
    Thread-safe singleton that manages the active development session.

    Usage
    -----
    from nova.session import get_dev_session_manager
    mgr = get_dev_session_manager()
    mgr.start_session()                          # call once on startup
    mgr.add_prompt("Add JWT auth", ai_response)  # after each turn
    intent = mgr.resolve_followup("continue")    # before each task
    goal   = mgr.build_followup_goal(intent)     # synthesise task goal
    mgr.record_task_start(task)                  # just before execute
    mgr.record_task_complete(task, report)        # when engine finishes
    mgr.undo_last_task()                         # on "undo" command
    """

    _instance: Optional["DevelopmentSessionManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "DevelopmentSessionManager":
        with cls._instance_lock:
            if cls._instance is None:
                obj = super().__new__(cls)
                obj._initialised = False
                cls._instance = obj
            return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self._session: Optional[DevelopmentSession] = None
        self._lock = threading.RLock()
        self._initialised = True

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def start_session(self, project_root: Optional[Path] = None) -> DevelopmentSession:
        """
        Start a new development session.

        Populates project metadata from ProjectAwarenessEngine (if a context
        is already available) and detects the current Git branch.

        Parameters
        ----------
        project_root : Path, optional
            Override the project root.  Defaults to what PAE reports.
        """
        with self._lock:
            session = DevelopmentSession()

            # Resolve project root
            root = project_root or self._resolve_project_root()
            session.project_root = root

            # Pull project metadata from PAE
            self._sync_project_metadata(session)

            # Detect git branch
            session.git_branch = self._detect_git_branch(root)

            self._session = session

        logger.info(
            "[Session] Started session %s — project=%s branch=%s",
            session.session_id[:8],
            session.project_name or str(root),
            session.git_branch or "unknown",
        )
        self._mirror_to_working_memory()
        return session

    def end_session(self) -> None:
        """Mark the session as ended and emit a summary log."""
        with self._lock:
            if self._session is None:
                return
            self._session.ended_at = time.time()

        s = self._session
        logger.info(
            "[Session] Ended session %s — duration=%.1fs tasks_completed=%d "
            "tasks_failed=%d files_created=%d files_modified=%d files_deleted=%d",
            s.session_id[:8],
            s.duration_s,
            s.tasks_completed,
            s.tasks_failed,
            len(s.files_created),
            len(s.files_modified),
            len(s.files_deleted),
        )

    def get_session(self) -> Optional[DevelopmentSession]:
        """Return the active session, or None if not started."""
        with self._lock:
            return self._session

    # ── Task lifecycle hooks ──────────────────────────────────────────────────

    def record_task_start(self, task) -> int:
        """
        Called just BEFORE TaskExecutionEngine.execute_task().

        Returns the current CodeEditor history length so an UndoEntry can be
        prepared.  The caller (or the engine hook) should store this value and
        pass it to record_task_complete().
        """
        with self._lock:
            if self._session is None:
                return 0
            self._session.current_task_id = task.id
            self._session.current_task_goal = task.goal_description
            # Clear redo stack — a new task invalidates any pending redo
            self._session.redo_stack.clear()

        checkpoint = self._editor_history_len()
        logger.info("[Session] Task started: %s", task.goal_description)
        self._mirror_to_working_memory()
        return checkpoint

    def record_task_complete(self, task, report, editor_checkpoint_len: int = 0) -> None:
        """
        Called after TaskExecutionEngine finishes a task (success or failure).

        Parameters
        ----------
        task : nova.task.models.Task
            The finished Task object.
        report : nova.task.models.TaskReport
            The compiled report from get_task_report().
        editor_checkpoint_len : int
            The CodeEditor history length captured at task start.
        """
        with self._lock:
            if self._session is None:
                return

            rec = TaskRecord(
                task_id=task.id,
                goal=task.goal_description,
                status=task.status.value,
                steps_executed=report.steps_executed,
                steps_completed=report.steps_completed,
                steps_failed=report.steps_failed,
                files_created=list(report.files_created),
                files_modified=list(report.files_modified),
                files_deleted=[],  # TEE does not yet surface deleted files
                rollbacks=list(report.rollbacks),
                validation_passed=report.validation_status,
                duration_s=report.total_execution_time_s,
            )
            self._session.task_history.append(rec)

            # Accumulate file sets
            self._session.files_created.update(report.files_created)
            self._session.files_modified.update(report.files_modified)
            self._session.current_task_id = None
            self._session.current_task_goal = None

            # Push onto undo stack only for completed tasks
            if task.status.value == "completed":
                entry = UndoEntry(
                    task_id=task.id,
                    task_goal=task.goal_description,
                    editor_checkpoint_len=editor_checkpoint_len,
                    files_affected=list(report.files_created) + list(report.files_modified),
                )
                self._session.undo_stack.append(entry)

        logger.info(
            "[Session] Task %s: status=%s files_created=%d files_modified=%d",
            task.goal_description,
            task.status.value,
            len(report.files_created),
            len(report.files_modified),
        )
        self._mirror_to_working_memory()

    # ── Conversation rolling window ───────────────────────────────────────────

    def add_prompt(self, user_text: str, ai_response: str = "") -> None:
        """
        Record a user prompt and the corresponding AI response.

        Updates the rolling window (max 10 items) used for context injection.
        """
        with self._lock:
            if self._session is None:
                return
            self._session.recent_prompts.append(user_text)
            if ai_response:
                self._session.recent_responses.append(ai_response)
        logger.debug("[Session] Recorded prompt turn.")

    # ── Follow-up intent resolution ───────────────────────────────────────────

    def resolve_followup(self, user_text: str) -> FollowupIntent:
        """
        Resolve user text to a FollowupIntent using the intent resolver.

        Returns FollowupIntent.NONE if the text is not a recognised follow-up.
        """
        return resolve_intent(user_text)

    def build_followup_goal(self, intent: FollowupIntent) -> Optional[str]:
        """
        Synthesise a concrete goal string for a given follow-up intent using
        current session state.

        Returns None for NONE / UNDO / REDO (those do not create new tasks).
        """
        with self._lock:
            s = self._session
            if s is None:
                return None

            last = s.last_task_record
            changed = s.all_changed_files

        goal_map = {
            FollowupIntent.CONTINUE: (
                f"Continue: {last.goal}" if last else None
            ),
            FollowupIntent.EXPLAIN: (
                f"Explain the code changes made in: {last.goal}" if last else None
            ),
            FollowupIntent.IMPROVE: (
                f"Improve the code created for: {last.goal}" if last else None
            ),
            FollowupIntent.REFACTOR: (
                f"Refactor the code in: {', '.join(changed)}"
                if changed else None
            ),
            FollowupIntent.ADD_TESTS: (
                f"Write unit tests for: {', '.join(changed)}"
                if changed else None
            ),
            FollowupIntent.OPTIMIZE: (
                f"Optimize the performance of: {', '.join(changed)}"
                if changed else None
            ),
            FollowupIntent.DOCUMENT: (
                f"Add docstrings and documentation to: {', '.join(changed)}"
                if changed else None
            ),
        }
        return goal_map.get(intent)

    # ── Undo / redo ───────────────────────────────────────────────────────────

    def undo_last_task(self) -> bool:
        """
        Undo the most recently completed task by rolling back CodeEditor history
        to the checkpoint stored in the UndoEntry.

        Returns True on success, False if nothing to undo.
        """
        with self._lock:
            if self._session is None or not self._session.undo_stack:
                logger.warning("[Session] Nothing to undo.")
                return False
            entry = self._session.undo_stack.pop()
            self._session.redo_stack.append(entry)

            # Remove the corresponding TaskRecord from history
            self._session.task_history = [
                r for r in self._session.task_history if r.task_id != entry.task_id
            ]

            # Remove the files from the session file sets
            for f in entry.files_affected:
                self._session.files_created.discard(f)
                self._session.files_modified.discard(f)

        # Rollback editor history to checkpoint (outside lock — editor has its own)
        editor = self._get_editor()
        if editor:
            rolled = 0
            while len(editor.history) > entry.editor_checkpoint_len:
                result = editor.rollback_last_change()
                if not result.success:
                    break
                rolled += 1
            logger.info(
                "[Session] Undo: reverted %d file change(s) from task '%s'",
                rolled,
                entry.task_goal,
            )

        self._mirror_to_working_memory()
        return True

    def redo_last_task(self) -> Optional[str]:
        """
        Redo the most recently undone task by re-executing its original goal
        through the TaskExecutionEngine.

        Returns the new task ID on success, None if nothing to redo.

        Note: Redo re-executes the original goal (may produce slightly different
        AI-generated code).  Deterministic redo via file snapshots is a future
        enhancement.
        """
        with self._lock:
            if self._session is None or not self._session.redo_stack:
                logger.warning("[Session] Nothing to redo.")
                return None
            entry = self._session.redo_stack.pop()
            goal = entry.task_goal

        logger.info("[Session] Redo: re-executing task '%s'", goal)
        try:
            from nova.task import get_task_execution_engine
            engine = get_task_execution_engine()
            task = engine.create_task(goal)
            checkpoint = self.record_task_start(task)
            engine.execute_task(task.id)
            return task.id
        except Exception as e:
            logger.error("[Session] Redo failed: %s", e)
            # Restore redo entry if execution couldn't start
            with self._lock:
                if self._session:
                    self._session.redo_stack.append(entry)
            return None

    # ── Context injection ─────────────────────────────────────────────────────

    def build_context_prompt(self) -> str:
        """
        Build a compact context string to prepend to every AI provider call.

        Returns an empty string if no session is active or context is empty.
        """
        with self._lock:
            s = self._session
            if s is None:
                return ""

            lines = ["[Session Context]"]

            if s.project_name:
                meta_parts = [s.project_name]
                if s.languages:
                    meta_parts.append(", ".join(s.languages))
                if s.frameworks:
                    meta_parts.append(", ".join(s.frameworks))
                lines.append(f"Project: {' — '.join(meta_parts)}")

            if s.git_branch:
                lines.append(f"Branch: {s.git_branch}")

            if s.current_task_goal:
                lines.append(f"Active task: {s.current_task_goal}")
            elif s.last_task_record:
                lines.append(f"Last task: {s.last_task_record.goal}")

            recent_files = sorted(
                list(s.files_created | s.files_modified)
            )[-5:]  # last 5 files
            if recent_files:
                lines.append(f"Recent files: {', '.join(recent_files)}")

            recent_prompts = list(s.recent_prompts)[-_MAX_RECENT_PROMPTS_IN_CONTEXT:]
            recent_responses = list(s.recent_responses)[-_MAX_RECENT_PROMPTS_IN_CONTEXT:]
            if recent_prompts:
                lines.append("Recent conversation:")
                for i, prompt in enumerate(recent_prompts):
                    lines.append(f"  User: {prompt[:120]}")
                    if i < len(recent_responses):
                        lines.append(f"  Nova: {recent_responses[i][:120]}")

            if len(lines) == 1:
                return ""  # only the header — nothing useful

            return "\n".join(lines)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_project_root(self) -> Path:
        try:
            from nova.project.engine import ProjectAwarenessEngine
            ctx = ProjectAwarenessEngine().get_context()
            if ctx:
                return ctx.root
        except Exception:
            pass
        return Path.cwd()

    def _sync_project_metadata(self, session: DevelopmentSession) -> None:
        """Populate session fields from ProjectAwarenessEngine context."""
        try:
            from nova.project.engine import ProjectAwarenessEngine
            ctx = ProjectAwarenessEngine().get_context()
            if ctx:
                session.project_name = ctx.name or ""
                session.project_root = ctx.root
                session.languages = list(ctx.languages or [])
                session.frameworks = list(ctx.frameworks or [])
        except Exception as e:
            logger.debug("[Session] Could not sync project metadata: %s", e)

    def _detect_git_branch(self, root: Optional[Path]) -> str:
        """Run git to detect the current branch name."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(root or Path.cwd()),
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _editor_history_len(self) -> int:
        """Return the current CodeEditor history length (0 if unavailable)."""
        editor = self._get_editor()
        return len(editor.history) if editor else 0

    def _get_editor(self):
        try:
            from nova.edit import get_code_editor
            return get_code_editor()
        except Exception:
            return None

    def _mirror_to_working_memory(self) -> None:
        """
        Mirror key session fields into WorkingMemory.session_state so that
        existing modules (ConversationManager, NLP pipeline, etc.) can read
        them without knowing about DevelopmentSession.
        """
        try:
            from nova.core.memory import get_working_memory
            wm = get_working_memory()
            with self._lock:
                s = self._session
                if s is None:
                    return
            wm.set("project_root", str(s.project_root) if s.project_root else None)
            wm.set("project_name", s.project_name or None)
            wm.set("project_languages", list(s.languages))
            wm.set("project_frameworks", list(s.frameworks))
            if s.current_task_goal:
                wm.set("active_task", s.current_task_goal)
        except Exception as e:
            logger.debug("[Session] Could not mirror to working memory: %s", e)
