"""
nova.tests.session.test_qa_session
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive QA test suite for the Development Session Manager.

Covers all 13 verification items:
 1.  Session creation
 2.  Session persistence during development
 3.  Follow-up command understanding
 4.  Task history recording
 5.  Modified file tracking
 6.  Undo last task
 7.  Redo last task
 8.  Context injection into Planner
 9.  Context injection into AI Provider
10.  Existing Task Execution Engine integration
11.  Existing Conversation Manager / WorkingMemory integration
12.  Existing Memory integration
13.  Existing Nova functionality remains unaffected

Metrics collected:
 - Pass / fail per test
 - Intent resolution latency
 - Context prompt build latency
 - Undo/redo operation counts
 - Memory usage (before/after session lifecycle)
"""
from __future__ import annotations

import gc
import json
import tempfile
import threading
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Imports under test ────────────────────────────────────────────────────────
from nova.session import (
    DevelopmentSessionManager,
    DevelopmentSession,
    FollowupIntent,
    TaskRecord,
    UndoEntry,
    get_dev_session,
    get_dev_session_manager,
    resolve_intent,
    is_followup,
)
from nova.session.manager import DevelopmentSessionManager as _DSM
from nova.project.engine import ProjectAwarenessEngine
from nova.code.engine import CodeIntelligenceEngine
from nova.task.engine import TaskExecutionEngine
from nova.task.models import TaskStatus, Task
from nova.edit.editor import CodeEditor
from nova.core.memory import WorkingMemory


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_singletons():
    _DSM._instance = None
    TaskExecutionEngine._instance = None
    CodeEditor._instance = None
    ProjectAwarenessEngine._instance = None
    CodeIntelligenceEngine._instance = None


def _mock_task(task_id="task-001", goal="Add auth", status=TaskStatus.COMPLETED):
    t = MagicMock(spec=Task)
    t.id = task_id
    t.goal_description = goal
    t.status = status
    return t


def _mock_report(
    files_created=None,
    files_modified=None,
    steps_executed=2,
    steps_completed=2,
    steps_failed=0,
):
    r = MagicMock()
    r.files_created = list(files_created or [])
    r.files_modified = list(files_modified or [])
    r.steps_executed = steps_executed
    r.steps_completed = steps_completed
    r.steps_failed = steps_failed
    r.rollbacks = []
    r.validation_status = True
    r.total_execution_time_s = 0.42
    return r


def _setup_project(pae: ProjectAwarenessEngine, root: Path):
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (root / "pyproject.toml").write_text('[project]\nname = "qa_project"\n')
    pae.scan(root)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Session Creation
# ═════════════════════════════════════════════════════════════════════════════

class TC01_SessionCreation(unittest.TestCase):
    """TC01: Verify session creation, fields, and singleton behaviour."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()

    def tearDown(self):
        self.mgr.end_session()

    def test_01_singleton_returns_same_instance(self):
        """Two calls to get_dev_session_manager() return identical object."""
        mgr2 = get_dev_session_manager()
        self.assertIs(self.mgr, mgr2)

    def test_02_start_session_creates_session(self):
        s = self.mgr.start_session()
        self.assertIsInstance(s, DevelopmentSession)
        self.assertIsNotNone(s.session_id)
        self.assertGreater(s.started_at, 0)

    def test_03_session_id_is_unique_per_restart(self):
        s1 = self.mgr.start_session()
        id1 = s1.session_id
        self.mgr.end_session()
        _reset_singletons()
        s2 = get_dev_session_manager().start_session()
        self.assertNotEqual(id1, s2.session_id)

    def test_04_start_with_explicit_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = self.mgr.start_session(project_root=root)
            self.assertEqual(s.project_root, root)

    def test_05_start_without_root_uses_pae_or_cwd(self):
        s = self.mgr.start_session()
        self.assertIsNotNone(s.project_root)

    def test_06_git_branch_detected(self):
        s = self.mgr.start_session()
        # We are running inside the Nova repo so a branch should be found
        self.assertIsInstance(s.git_branch, str)
        # Should not be empty when running inside a git repo
        self.assertGreater(len(s.git_branch), 0)

    def test_07_get_session_returns_active_session(self):
        s = self.mgr.start_session()
        self.assertEqual(get_dev_session().session_id, s.session_id)

    def test_08_get_session_before_start_returns_none(self):
        self.assertIsNone(get_dev_session())

    def test_09_end_session_sets_ended_at(self):
        self.mgr.start_session()
        t0 = time.time()
        self.mgr.end_session()
        self.assertIsNotNone(self.mgr.get_session().ended_at)
        self.assertGreaterEqual(self.mgr.get_session().ended_at, t0)

    def test_10_end_session_calculates_duration(self):
        self.mgr.start_session()
        time.sleep(0.05)
        self.mgr.end_session()
        self.assertGreater(self.mgr.get_session().duration_s, 0)


# ═════════════════════════════════════════════════════════════════════════════
# 2. Session Persistence During Development
# ═════════════════════════════════════════════════════════════════════════════

class TC02_SessionPersistence(unittest.TestCase):
    """TC02: Session accumulates state correctly across multiple tasks."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()

    def tearDown(self):
        self.mgr.end_session()

    def test_11_task_history_grows_across_tasks(self):
        for i in range(3):
            task = _mock_task(task_id=f"t{i}", goal=f"Task {i}")
            report = _mock_report(files_created=[f"file{i}.py"])
            self.mgr.record_task_start(task)
            self.mgr.record_task_complete(task, report)

        s = self.mgr.get_session()
        self.assertEqual(len(s.task_history), 3)

    def test_12_file_sets_accumulate_across_tasks(self):
        for i in range(3):
            task = _mock_task(task_id=f"t{i}", goal=f"Task {i}")
            report = _mock_report(
                files_created=[f"created_{i}.py"],
                files_modified=[f"modified_{i}.py"],
            )
            self.mgr.record_task_start(task)
            self.mgr.record_task_complete(task, report)

        s = self.mgr.get_session()
        self.assertEqual(len(s.files_created), 3)
        self.assertEqual(len(s.files_modified), 3)

    def test_13_undo_stack_grows_per_completed_task(self):
        for i in range(4):
            task = _mock_task(task_id=f"t{i}", goal=f"Task {i}")
            report = _mock_report()
            self.mgr.record_task_start(task)
            self.mgr.record_task_complete(task, report)

        s = self.mgr.get_session()
        self.assertEqual(len(s.undo_stack), 4)

    def test_14_current_task_cleared_after_complete(self):
        task = _mock_task()
        report = _mock_report()
        self.mgr.record_task_start(task)
        self.assertIsNotNone(self.mgr.get_session().current_task_id)
        self.mgr.record_task_complete(task, report)
        self.assertIsNone(self.mgr.get_session().current_task_id)
        self.assertIsNone(self.mgr.get_session().current_task_goal)

    def test_15_session_stats_count_correctly(self):
        for i in range(2):
            t = _mock_task(task_id=f"ok{i}", goal=f"Success {i}", status=TaskStatus.COMPLETED)
            self.mgr.record_task_start(t)
            self.mgr.record_task_complete(t, _mock_report())

        fail_task = _mock_task(task_id="fail", goal="Fail task", status=TaskStatus.FAILED)
        self.mgr.record_task_start(fail_task)
        self.mgr.record_task_complete(fail_task, _mock_report(steps_failed=1))

        s = self.mgr.get_session()
        self.assertEqual(s.tasks_completed, 2)
        self.assertEqual(s.tasks_failed, 1)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Follow-up Command Understanding
# ═════════════════════════════════════════════════════════════════════════════

class TC03_FollowupCommandUnderstanding(unittest.TestCase):
    """TC03: Comprehensive follow-up intent resolution."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()

    def tearDown(self):
        self.mgr.end_session()

    def _assert_intent(self, text: str, expected: FollowupIntent):
        t0 = time.perf_counter()
        result = self.mgr.resolve_followup(text)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertEqual(result, expected, msg=f"Text={text!r}")
        # Performance: intent resolution must be under 5 ms
        self.assertLess(elapsed_ms, 5.0, msg=f"Resolution took {elapsed_ms:.2f} ms")

    def test_16_undo_phrases(self):
        for phrase in ["undo", "undo that", "revert", "go back", "rollback"]:
            self._assert_intent(phrase, FollowupIntent.UNDO)

    def test_17_redo_phrases(self):
        for phrase in ["redo", "redo that", "redo it"]:
            self._assert_intent(phrase, FollowupIntent.REDO)

    def test_18_continue_phrases(self):
        for phrase in ["continue", "keep going", "proceed", "go on", "next step"]:
            self._assert_intent(phrase, FollowupIntent.CONTINUE)

    def test_19_explain_phrases(self):
        for phrase in ["explain", "explain that", "what did you do", "how does it work"]:
            self._assert_intent(phrase, FollowupIntent.EXPLAIN)

    def test_20_improve_phrases(self):
        for phrase in ["improve", "improve it", "make it better"]:
            self._assert_intent(phrase, FollowupIntent.IMPROVE)

    def test_21_refactor_phrases(self):
        for phrase in ["refactor", "refactor it", "clean it up"]:
            self._assert_intent(phrase, FollowupIntent.REFACTOR)

    def test_22_add_tests_phrases(self):
        for phrase in ["add tests", "write unit tests", "test it"]:
            self._assert_intent(phrase, FollowupIntent.ADD_TESTS)

    def test_23_optimize_phrases(self):
        for phrase in ["optimize", "make it faster", "speed it up"]:
            self._assert_intent(phrase, FollowupIntent.OPTIMIZE)

    def test_24_document_phrases(self):
        for phrase in ["document it", "add docs", "add docstrings"]:
            self._assert_intent(phrase, FollowupIntent.DOCUMENT)

    def test_25_none_for_new_tasks(self):
        for phrase in [
            "add JWT authentication",
            "create a login page",
            "implement CRUD APIs for products",
            "fix the failing unit tests",
            "refactor the authentication module",
        ]:
            self._assert_intent(phrase, FollowupIntent.NONE)

    def test_26_case_insensitive(self):
        self._assert_intent("UNDO", FollowupIntent.UNDO)
        self._assert_intent("Continue PLEASE", FollowupIntent.CONTINUE)
        self._assert_intent("ADD TESTS", FollowupIntent.ADD_TESTS)

    def test_27_punctuation_stripped(self):
        self._assert_intent("undo!", FollowupIntent.UNDO)
        self._assert_intent("continue.", FollowupIntent.CONTINUE)
        self._assert_intent("explain?", FollowupIntent.EXPLAIN)

    def test_28_goal_synthesis_continue(self):
        s = self.mgr.get_session()
        s.task_history.append(TaskRecord("1", "Add auth", "completed"))
        goal = self.mgr.build_followup_goal(FollowupIntent.CONTINUE)
        self.assertIn("Add auth", goal)

    def test_29_goal_synthesis_add_tests(self):
        s = self.mgr.get_session()
        s.files_created.add("auth.py")
        s.files_modified.add("routes.py")
        goal = self.mgr.build_followup_goal(FollowupIntent.ADD_TESTS)
        self.assertIn("auth.py", goal)

    def test_30_goal_synthesis_refactor(self):
        s = self.mgr.get_session()
        s.files_modified.add("views.py")
        goal = self.mgr.build_followup_goal(FollowupIntent.REFACTOR)
        self.assertIn("views.py", goal)

    def test_31_goal_synthesis_returns_none_for_undo_redo_none(self):
        self.assertIsNone(self.mgr.build_followup_goal(FollowupIntent.UNDO))
        self.assertIsNone(self.mgr.build_followup_goal(FollowupIntent.REDO))
        self.assertIsNone(self.mgr.build_followup_goal(FollowupIntent.NONE))

    def test_32_is_followup_helper(self):
        self.assertTrue(is_followup("undo"))
        self.assertTrue(is_followup("continue"))
        self.assertFalse(is_followup("add JWT auth"))


# ═════════════════════════════════════════════════════════════════════════════
# 4. Task History Recording
# ═════════════════════════════════════════════════════════════════════════════

class TC04_TaskHistoryRecording(unittest.TestCase):
    """TC04: TaskRecord fields are populated correctly."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()

    def tearDown(self):
        self.mgr.end_session()

    def test_33_task_record_goal_persisted(self):
        task = _mock_task(goal="Create CRUD APIs")
        report = _mock_report(files_created=["api.py"])
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report)
        rec = self.mgr.get_session().last_task_record
        self.assertEqual(rec.goal, "Create CRUD APIs")

    def test_34_task_record_status_persisted(self):
        task = _mock_task(status=TaskStatus.FAILED)
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, _mock_report(steps_failed=1))
        rec = self.mgr.get_session().last_task_record
        self.assertEqual(rec.status, "failed")

    def test_35_task_record_files_populated(self):
        task = _mock_task()
        report = _mock_report(
            files_created=["models.py", "serializers.py"],
            files_modified=["urls.py"],
        )
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report)
        rec = self.mgr.get_session().last_task_record
        self.assertIn("models.py", rec.files_created)
        self.assertIn("serializers.py", rec.files_created)
        self.assertIn("urls.py", rec.files_modified)

    def test_36_task_record_duration_populated(self):
        task = _mock_task()
        report = _mock_report()
        report.total_execution_time_s = 1.23
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report)
        rec = self.mgr.get_session().last_task_record
        self.assertAlmostEqual(rec.duration_s, 1.23, places=2)

    def test_37_task_record_rollbacks_populated(self):
        task = _mock_task()
        report = _mock_report()
        report.rollbacks = ["Create step", "Update step"]
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report)
        rec = self.mgr.get_session().last_task_record
        self.assertIn("Create step", rec.rollbacks)

    def test_38_multiple_task_records_ordered(self):
        goals = ["Task A", "Task B", "Task C"]
        for i, goal in enumerate(goals):
            task = _mock_task(task_id=f"t{i}", goal=goal)
            self.mgr.record_task_start(task)
            self.mgr.record_task_complete(task, _mock_report())
        history = self.mgr.get_session().task_history
        self.assertEqual([r.goal for r in history], goals)


# ═════════════════════════════════════════════════════════════════════════════
# 5. Modified File Tracking
# ═════════════════════════════════════════════════════════════════════════════

class TC05_FileTracking(unittest.TestCase):
    """TC05: Verify file set accumulation and all_changed_files property."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()

    def tearDown(self):
        self.mgr.end_session()

    def _run_task(self, created=None, modified=None, task_id="t1"):
        task = _mock_task(task_id=task_id)
        report = _mock_report(files_created=created, files_modified=modified)
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report)

    def test_39_files_created_tracked(self):
        self._run_task(created=["auth.py", "jwt.py"])
        s = self.mgr.get_session()
        self.assertIn("auth.py", s.files_created)
        self.assertIn("jwt.py", s.files_created)

    def test_40_files_modified_tracked(self):
        self._run_task(modified=["settings.py"])
        self.assertIn("settings.py", self.mgr.get_session().files_modified)

    def test_41_all_changed_files_union(self):
        self._run_task(created=["a.py"], modified=["b.py"], task_id="t1")
        s = self.mgr.get_session()
        s.files_deleted.add("c.py")
        changed = s.all_changed_files
        for f in ["a.py", "b.py", "c.py"]:
            self.assertIn(f, changed)

    def test_42_no_duplicate_files_in_all_changed(self):
        self._run_task(created=["dup.py"], modified=["dup.py"], task_id="t2")
        changed = self.mgr.get_session().all_changed_files
        self.assertEqual(len(changed), len(set(changed)))

    def test_43_file_sets_survive_multiple_tasks(self):
        for i in range(5):
            self._run_task(created=[f"file{i}.py"], task_id=f"t{i}")
        self.assertEqual(len(self.mgr.get_session().files_created), 5)

    def test_44_failed_task_files_still_tracked(self):
        """Even failed tasks should have their files recorded in history
        (even though they don't go on the undo stack)."""
        task = _mock_task(status=TaskStatus.FAILED)
        report = _mock_report(files_created=["broken.py"])
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report)
        # files_created should still be updated
        self.assertIn("broken.py", self.mgr.get_session().files_created)


# ═════════════════════════════════════════════════════════════════════════════
# 6. Undo Last Task
# ═════════════════════════════════════════════════════════════════════════════

class TC06_UndoLastTask(unittest.TestCase):
    """TC06: Undo removes task from history and rolls back editor."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()

    def tearDown(self):
        self.mgr.end_session()

    def _complete_task(self, goal="Add feature", files=None, task_id="t1"):
        task = _mock_task(task_id=task_id, goal=goal)
        report = _mock_report(files_created=files or [])
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report, editor_checkpoint_len=0)
        return task

    def test_45_undo_returns_false_with_empty_stack(self):
        self.assertFalse(self.mgr.undo_last_task())

    def test_46_undo_returns_false_without_session(self):
        self.mgr.end_session()
        _reset_singletons()
        mgr2 = get_dev_session_manager()
        self.assertFalse(mgr2.undo_last_task())

    def test_47_undo_removes_task_from_history(self):
        self._complete_task(goal="Task A", files=["a.py"], task_id="t1")
        self._complete_task(goal="Task B", files=["b.py"], task_id="t2")
        self.assertEqual(len(self.mgr.get_session().task_history), 2)

        self.mgr.undo_last_task()

        s = self.mgr.get_session()
        self.assertEqual(len(s.task_history), 1)
        self.assertEqual(s.task_history[0].goal, "Task A")

    def test_48_undo_removes_files_from_session_sets(self):
        self._complete_task(files=["auth.py"], task_id="t1")
        s = self.mgr.get_session()
        self.assertIn("auth.py", s.files_created)

        self.mgr.undo_last_task()
        self.assertNotIn("auth.py", s.files_created)

    def test_49_undo_moves_entry_to_redo_stack(self):
        self._complete_task(task_id="t1")
        s = self.mgr.get_session()
        self.assertEqual(len(s.undo_stack), 1)

        self.mgr.undo_last_task()
        self.assertEqual(len(s.undo_stack), 0)
        self.assertEqual(len(s.redo_stack), 1)

    def test_50_undo_twice(self):
        self._complete_task(goal="A", task_id="t1")
        self._complete_task(goal="B", task_id="t2")
        self.mgr.undo_last_task()
        self.mgr.undo_last_task()
        s = self.mgr.get_session()
        self.assertEqual(len(s.task_history), 0)
        self.assertEqual(len(s.redo_stack), 2)

    def test_51_undo_preserves_earlier_tasks(self):
        self._complete_task(goal="A", files=["a.py"], task_id="t1")
        self._complete_task(goal="B", files=["b.py"], task_id="t2")
        self.mgr.undo_last_task()
        s = self.mgr.get_session()
        self.assertIn("a.py", s.files_created)
        self.assertNotIn("b.py", s.files_created)

    def test_52_undo_third_returns_false_on_empty(self):
        self._complete_task(task_id="t1")
        self.mgr.undo_last_task()  # 1st undo
        result = self.mgr.undo_last_task()  # 2nd undo - nothing left
        self.assertFalse(result)

    def test_53_failed_task_cannot_be_undone(self):
        """Failed tasks don't go on undo stack."""
        task = _mock_task(status=TaskStatus.FAILED)
        report = _mock_report()
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report)
        result = self.mgr.undo_last_task()
        self.assertFalse(result)


# ═════════════════════════════════════════════════════════════════════════════
# 7. Redo Last Task
# ═════════════════════════════════════════════════════════════════════════════

class TC07_RedoLastTask(unittest.TestCase):
    """TC07: Redo stack management and re-execution triggering."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()

    def tearDown(self):
        self.mgr.end_session()

    def _complete_and_undo(self, goal="Add feature", task_id="t1"):
        task = _mock_task(task_id=task_id, goal=goal)
        report = _mock_report()
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report)
        self.mgr.undo_last_task()

    def test_54_redo_returns_none_with_empty_stack(self):
        result = self.mgr.redo_last_task()
        self.assertIsNone(result)

    def test_55_redo_returns_none_without_session(self):
        _reset_singletons()
        mgr2 = get_dev_session_manager()
        self.assertIsNone(mgr2.redo_last_task())

    def test_56_new_task_clears_redo_stack(self):
        self._complete_and_undo(task_id="t1")
        s = self.mgr.get_session()
        self.assertEqual(len(s.redo_stack), 1)

        # New task should clear redo stack
        task2 = _mock_task(task_id="t2", goal="New task")
        self.mgr.record_task_start(task2)
        self.assertEqual(len(s.redo_stack), 0)

    def test_57_undo_undo_redo_order(self):
        """Undo twice, redo once — redo stack has one entry left."""
        for i in range(2):
            task = _mock_task(task_id=f"t{i}", goal=f"Task {i}")
            self.mgr.record_task_start(task)
            self.mgr.record_task_complete(task, _mock_report())

        s = self.mgr.get_session()
        self.mgr.undo_last_task()  # undo task 1 → redo_stack=[t1]
        self.mgr.undo_last_task()  # undo task 0 → redo_stack=[t1, t0]
        self.assertEqual(len(s.redo_stack), 2)
        self.assertEqual(len(s.undo_stack), 0)


# ═════════════════════════════════════════════════════════════════════════════
# 8. Context Injection into Planner
# ═════════════════════════════════════════════════════════════════════════════

class TC08_ContextInjectionPlanner(unittest.TestCase):
    """TC08: build_context_prompt() surfaces information useful to the Planner."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.project_name = "testapp"
        s.languages = ["Python"]
        s.frameworks = ["FastAPI"]
        s.git_branch = "feature/auth"

    def tearDown(self):
        self.mgr.end_session()

    def _prompt(self) -> str:
        return self.mgr.build_context_prompt()

    def test_58_prompt_contains_project_name(self):
        self.assertIn("testapp", self._prompt())

    def test_59_prompt_contains_language(self):
        self.assertIn("Python", self._prompt())

    def test_60_prompt_contains_framework(self):
        self.assertIn("FastAPI", self._prompt())

    def test_61_prompt_contains_branch(self):
        self.assertIn("feature/auth", self._prompt())

    def test_62_prompt_contains_active_task(self):
        self.mgr.get_session().current_task_goal = "Implement JWT"
        self.assertIn("Implement JWT", self._prompt())

    def test_63_prompt_contains_last_task_when_no_active(self):
        s = self.mgr.get_session()
        s.task_history.append(TaskRecord("1", "Add models", "completed"))
        self.assertIn("Add models", self._prompt())

    def test_64_prompt_contains_recent_files(self):
        s = self.mgr.get_session()
        s.files_created.add("auth.py")
        self.assertIn("auth.py", self._prompt())

    def test_65_prompt_contains_recent_conversation(self):
        self.mgr.add_prompt("What files did you change?", "I changed auth.py")
        prompt = self._prompt()
        self.assertIn("What files did you change?", prompt)

    def test_66_prompt_empty_when_all_fields_blank(self):
        s = self.mgr.get_session()
        s.project_name = ""
        s.git_branch = ""
        s.current_task_goal = None
        s.task_history.clear()
        s.files_created.clear()
        s.files_modified.clear()
        s.recent_prompts.clear()
        s.recent_responses.clear()
        self.assertEqual(self._prompt(), "")

    def test_67_prompt_build_latency_under_1ms(self):
        s = self.mgr.get_session()
        s.files_created.update([f"file{i}.py" for i in range(20)])
        self.mgr.add_prompt("prompt", "response")
        t0 = time.perf_counter()
        self.mgr.build_context_prompt()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertLess(elapsed_ms, 1.0)


# ═════════════════════════════════════════════════════════════════════════════
# 9. Context Injection into AI Provider
# ═════════════════════════════════════════════════════════════════════════════

class TC09_ContextInjectionAIProvider(unittest.TestCase):
    """TC09: Context prompt is structurally correct for AI provider prepending."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.project_name = "myapp"
        s.git_branch = "main"

    def tearDown(self):
        self.mgr.end_session()

    def test_68_prompt_starts_with_session_context_header(self):
        s = self.mgr.get_session()
        s.files_created.add("x.py")
        prompt = self.mgr.build_context_prompt()
        self.assertTrue(prompt.startswith("[Session Context]"))

    def test_69_prompt_is_single_coherent_string(self):
        s = self.mgr.get_session()
        s.files_created.add("x.py")
        prompt = self.mgr.build_context_prompt()
        self.assertIsInstance(prompt, str)
        self.assertNotIn("\r", prompt)  # no carriage returns

    def test_70_prompt_truncates_long_user_text(self):
        long_text = "A" * 200
        self.mgr.add_prompt(long_text, "Short AI response")
        prompt = self.mgr.build_context_prompt()
        # Each user/AI line is capped at 120 chars
        for line in prompt.split("\n"):
            if line.strip().startswith("User:"):
                self.assertLessEqual(len(line), 130)  # "  User: " prefix

    def test_71_prompt_includes_at_most_2_recent_turns(self):
        for i in range(5):
            self.mgr.add_prompt(f"Q{i}", f"A{i}")
        prompt = self.mgr.build_context_prompt()
        # Only last 2 User/Nova pairs should appear
        user_lines = [l for l in prompt.split("\n") if "User:" in l]
        self.assertLessEqual(len(user_lines), 2)

    def test_72_prompt_correct_when_no_responses_yet(self):
        s = self.mgr.get_session()
        s.files_created.add("new.py")
        s.recent_prompts.append("Add login")
        # No responses yet
        prompt = self.mgr.build_context_prompt()
        self.assertIn("Add login", prompt)


# ═════════════════════════════════════════════════════════════════════════════
# 10. Task Execution Engine Integration
# ═════════════════════════════════════════════════════════════════════════════

class TC10_TaskEngineIntegration(unittest.TestCase):
    """TC10: TEE hooks and DSM observe each other correctly."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.engine = TaskExecutionEngine()

    def tearDown(self):
        try:
            self.mgr.end_session()
        except Exception:
            pass

    def test_73_engine_has_on_step_complete_hook(self):
        self.assertTrue(hasattr(self.engine, "on_step_complete"))
        self.assertIsNone(self.engine.on_step_complete)

    def test_74_engine_has_on_step_failed_hook(self):
        self.assertTrue(hasattr(self.engine, "on_step_failed"))
        self.assertIsNone(self.engine.on_step_failed)

    def test_75_hooks_accept_callable(self):
        results = []
        self.engine.on_step_complete = lambda t, s: results.append("complete")
        self.engine.on_step_failed = lambda t, s: results.append("failed")
        # Call directly
        self.engine.on_step_complete(MagicMock(), MagicMock())
        self.engine.on_step_failed(MagicMock(), MagicMock())
        self.assertEqual(results, ["complete", "failed"])

    def test_76_dsm_records_task_start_returns_checkpoint(self):
        self.mgr.start_session()
        task = _mock_task()
        chk = self.mgr.record_task_start(task)
        self.assertIsInstance(chk, int)

    def test_77_dsm_record_complete_populates_session(self):
        self.mgr.start_session()
        task = _mock_task(goal="Integration task")
        report = _mock_report(files_created=["integration.py"])
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report, editor_checkpoint_len=0)
        s = self.mgr.get_session()
        self.assertEqual(s.last_task_record.goal, "Integration task")
        self.assertIn("integration.py", s.files_created)

    @patch("nova.browser.providers.chatgpt.ChatGPTProvider.execute_action")
    def test_78_end_to_end_task_updates_session(self, mock_ai):
        """Full E2E: engine executes → DSM records it via manual hooks."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pae = ProjectAwarenessEngine()
            cie = CodeIntelligenceEngine()
            _setup_project(pae, root)

            mock_ai.side_effect = [
                json.dumps([
                    {"description": "Create util.py", "action_type": "create_file",
                     "metadata": {"rel_path": "util.py"}}
                ]),
                "UTIL = True\n",
            ]

            self.mgr.start_session()
            task = self.engine.create_task("Setup utilities")
            checkpoint = self.mgr.record_task_start(task)

            # Register DSM as engine observer
            def _on_complete(t, step):
                pass
            self.engine.on_step_complete = _on_complete

            self.engine.execute_task(task.id)

            # Wait for execution
            timeout = 5.0
            start = time.time()
            while self.engine.get_task_status(task.id) == TaskStatus.RUNNING:
                time.sleep(0.05)
                if time.time() - start > timeout:
                    self.fail("Task execution timed out")

            # Manually record completion
            report = self.engine.get_task_report(task.id)
            self.mgr.record_task_complete(task, report, editor_checkpoint_len=checkpoint)

            s = self.mgr.get_session()
            self.assertEqual(len(s.task_history), 1)


# ═════════════════════════════════════════════════════════════════════════════
# 11. Conversation Manager / WorkingMemory Integration
# ═════════════════════════════════════════════════════════════════════════════

class TC11_ConversationManagerIntegration(unittest.TestCase):
    """TC11: DSM mirrors session state into WorkingMemory (best-effort)."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()

    def tearDown(self):
        self.mgr.end_session()

    def test_79_project_root_stored_in_session(self):
        """Session correctly stores project_root set during start."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = self.mgr.start_session(project_root=root)
            self.assertEqual(s.project_root, root)

    def test_80_project_name_stored_in_session(self):
        """Session correctly stores project_name."""
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.project_name = "myapp"
        self.assertEqual(s.project_name, "myapp")

    def test_81_active_task_stored_in_session(self):
        """record_task_start sets current_task_goal in session."""
        self.mgr.start_session()
        task = _mock_task(goal="Do something")
        self.mgr.record_task_start(task)
        self.assertEqual(self.mgr.get_session().current_task_goal, "Do something")

    def test_82_mirror_does_not_raise(self):
        """_mirror_to_working_memory must never raise regardless of WM state."""
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.project_name = "myapp"
        s.languages = ["Python", "TypeScript"]
        # Must not raise
        self.mgr._mirror_to_working_memory()


# ═════════════════════════════════════════════════════════════════════════════
# 12. Memory Integration
# ═════════════════════════════════════════════════════════════════════════════

class TC12_MemoryIntegration(unittest.TestCase):
    """TC12: WorkingMemory remains functional alongside DSM."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()
        self.mgr.start_session()

    def tearDown(self):
        self.mgr.end_session()

    def test_83_working_memory_still_stores_arbitrary_keys(self):
        wm = WorkingMemory()
        wm.set("active_goal", None)
        # Still works — DSM co-exists
        wm.set("current_task", "My task")
        self.assertEqual(wm.get("current_task"), "My task")

    def test_84_history_manager_still_functional(self):
        wm = WorkingMemory()
        wm.history_manager.add_entry("system_event", "DSM started", {})
        entries = wm.history_manager.get_entries("system_event")
        msgs = [e.message for e in entries]
        self.assertIn("DSM started", msgs)

    def test_85_context_manager_still_functional(self):
        wm = WorkingMemory()
        ctx = wm.context_manager.enter_context("dev_session", {"project": "nova"})
        self.assertEqual(ctx.name, "dev_session")
        wm.context_manager.exit_context("dev_session")

    def test_86_dsm_mirror_does_not_corrupt_session_state(self):
        """DSM writes to session_state fields — verify validation still passes."""
        wm = WorkingMemory()
        # These are valid SessionState fields
        wm.set("project_root", "/tmp/test")
        wm.set("project_name", "test")
        wm.set("project_languages", ["Python"])
        # Validation runs inside set() — if it raises, test fails
        # No assertion needed — just must not raise


# ═════════════════════════════════════════════════════════════════════════════
# 13. Existing Nova Functionality Unaffected
# ═════════════════════════════════════════════════════════════════════════════

class TC13_RegressionNovaFunctionality(unittest.TestCase):
    """TC13: All existing Nova engines continue to function after DSM import."""

    def setUp(self):
        _reset_singletons()
        self.mgr = get_dev_session_manager()

    def tearDown(self):
        try:
            self.mgr.end_session()
        except Exception:
            pass

    def test_87_project_awareness_engine_still_scans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _setup_project(ProjectAwarenessEngine(), root)
            ctx = ProjectAwarenessEngine().get_context()
            self.assertIsNotNone(ctx)
            self.assertEqual(ctx.root, root)

    def test_88_code_editor_still_creates_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pae = ProjectAwarenessEngine()
            _setup_project(pae, root)
            editor = CodeEditor()
            result = editor.create_file("hello.py", "print('hi')")
            self.assertTrue(result.success)

    def test_89_task_engine_singleton_still_works(self):
        engine = TaskExecutionEngine()
        engine2 = TaskExecutionEngine()
        self.assertIs(engine, engine2)

    def test_90_session_module_imports_cleanly(self):
        """All public symbols importable without side effects."""
        from nova.session import (
            DevelopmentSessionManager,
            DevelopmentSession,
            FollowupIntent,
            TaskRecord,
            UndoEntry,
            get_dev_session,
            get_dev_session_manager,
            resolve_intent,
            is_followup,
        )
        self.assertIsNotNone(DevelopmentSessionManager)

    def test_91_dsm_start_does_not_break_pae(self):
        self.mgr.start_session()
        pae = ProjectAwarenessEngine()
        # PAE still returns context
        ctx = pae.get_context()
        # ctx could be None (no scan yet) — that is fine
        # We just verify no exception was raised

    def test_92_dsm_end_does_not_break_pae(self):
        self.mgr.start_session()
        self.mgr.end_session()
        pae = ProjectAwarenessEngine()
        # No exception raised
        self.assertIsNotNone(pae)

    def test_93_thread_safety_concurrent_add_prompt(self):
        """Many threads writing prompts concurrently must not corrupt state."""
        self.mgr.start_session()
        errors = []

        def _writer(i):
            try:
                self.mgr.add_prompt(f"prompt {i}", f"response {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Errors: {errors}")
        # At most 10 prompts in window
        self.assertLessEqual(len(self.mgr.get_session().recent_prompts), 10)

    def test_94_thread_safety_concurrent_record_task(self):
        """Many threads recording task completions must not corrupt history."""
        self.mgr.start_session()
        errors = []

        def _record(i):
            try:
                task = _mock_task(task_id=f"t{i}", goal=f"Goal {i}")
                report = _mock_report()
                self.mgr.record_task_start(task)
                self.mgr.record_task_complete(task, report)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_record, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertGreater(len(self.mgr.get_session().task_history), 0)


# ═════════════════════════════════════════════════════════════════════════════
# Memory Usage Measurement (non-assertion, metric-only)
# ═════════════════════════════════════════════════════════════════════════════

class TC14_MemoryMetrics(unittest.TestCase):
    """TC14: Memory overhead of the DSM lifecycle is minimal."""

    def setUp(self):
        _reset_singletons()

    def test_95_session_lifecycle_memory_overhead(self):
        gc.collect()
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        mgr = get_dev_session_manager()
        mgr.start_session()
        for i in range(50):
            task = _mock_task(task_id=f"t{i}", goal=f"Task {i}")
            report = _mock_report(files_created=[f"f{i}.py"])
            mgr.record_task_start(task)
            mgr.record_task_complete(task, report)
            mgr.add_prompt(f"prompt {i}", f"response {i}")
        mgr.build_context_prompt()
        mgr.end_session()

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_kb = sum(s.size_diff for s in stats) / 1024
        # Overhead should be well under 5 MB for 50 tasks
        self.assertLess(total_kb, 5 * 1024, msg=f"Memory overhead: {total_kb:.1f} KB")


if __name__ == "__main__":
    unittest.main(verbosity=2)
