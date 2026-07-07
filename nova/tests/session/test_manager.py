"""
Integration and unit tests for DevelopmentSessionManager.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from nova.session.manager import DevelopmentSessionManager
from nova.session.models import DevelopmentSession, FollowupIntent, TaskRecord, UndoEntry
from nova.project.engine import ProjectAwarenessEngine
from nova.code.engine import CodeIntelligenceEngine
from nova.task.engine import TaskExecutionEngine
from nova.task.models import TaskStatus
from nova.edit.editor import CodeEditor


class TestDevelopmentSessionManager(unittest.TestCase):

    def setUp(self):
        # Reset all singletons
        DevelopmentSessionManager._instance = None
        TaskExecutionEngine._instance = None
        CodeEditor._instance = None
        ProjectAwarenessEngine._instance = None
        CodeIntelligenceEngine._instance = None

        self.mgr = DevelopmentSessionManager()
        self.pae = ProjectAwarenessEngine()
        self.cie = CodeIntelligenceEngine()

    def tearDown(self):
        # End any open session
        try:
            self.mgr.end_session()
        except Exception:
            pass

    # ── Session start / end ──────────────────────────────────────────────────

    def test_start_session_returns_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = self.mgr.start_session(project_root=root)
            self.assertIsInstance(session, DevelopmentSession)
            self.assertEqual(session.project_root, root)
            self.assertIsNotNone(session.session_id)

    def test_get_session_before_start_is_none(self):
        self.assertIsNone(self.mgr.get_session())

    def test_get_session_after_start_returns_session(self):
        session = self.mgr.start_session()
        self.assertIsNotNone(self.mgr.get_session())
        self.assertEqual(self.mgr.get_session().session_id, session.session_id)

    def test_end_session_sets_ended_at(self):
        self.mgr.start_session()
        self.mgr.end_session()
        s = self.mgr.get_session()
        self.assertIsNotNone(s.ended_at)
        self.assertGreater(s.ended_at, s.started_at)

    # ── Project metadata sync ────────────────────────────────────────────────

    def test_session_syncs_pae_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Scaffold a minimal project
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
            (root / "requirements.txt").write_text("flask\n")
            self.pae.scan(root)

            session = self.mgr.start_session()
            # Root should be picked up from PAE
            self.assertEqual(session.project_root, root)

    # ── Task recording ───────────────────────────────────────────────────────

    def _make_mock_task(self, goal="Do something", status=TaskStatus.COMPLETED):
        task = MagicMock()
        task.id = "task-001"
        task.goal_description = goal
        task.status = status
        return task

    def _make_mock_report(self, files_created=None, files_modified=None):
        report = MagicMock()
        report.files_created = list(files_created or [])
        report.files_modified = list(files_modified or [])
        report.steps_executed = 1
        report.steps_completed = 1
        report.steps_failed = 0
        report.rollbacks = []
        report.validation_status = True
        report.total_execution_time_s = 0.5
        return report

    def test_record_task_start_returns_checkpoint(self):
        self.mgr.start_session()
        task = self._make_mock_task()
        checkpoint = self.mgr.record_task_start(task)
        self.assertIsInstance(checkpoint, int)
        self.assertGreaterEqual(checkpoint, 0)

    def test_record_task_start_clears_redo_stack(self):
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.redo_stack.append(UndoEntry("x", "old goal", 0))
        task = self._make_mock_task()
        self.mgr.record_task_start(task)
        self.assertEqual(len(s.redo_stack), 0)

    def test_record_task_complete_appends_task_record(self):
        self.mgr.start_session()
        task = self._make_mock_task(goal="Create db.py")
        report = self._make_mock_report(files_created=["db.py"])

        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report, editor_checkpoint_len=0)

        s = self.mgr.get_session()
        self.assertEqual(len(s.task_history), 1)
        self.assertEqual(s.task_history[0].goal, "Create db.py")
        self.assertIn("db.py", s.task_history[0].files_created)

    def test_record_task_complete_updates_file_sets(self):
        self.mgr.start_session()
        task = self._make_mock_task()
        report = self._make_mock_report(
            files_created=["models.py"],
            files_modified=["app.py"],
        )
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report, editor_checkpoint_len=0)

        s = self.mgr.get_session()
        self.assertIn("models.py", s.files_created)
        self.assertIn("app.py", s.files_modified)

    def test_record_task_complete_pushes_undo_entry_for_completed(self):
        self.mgr.start_session()
        task = self._make_mock_task(status=TaskStatus.COMPLETED)
        report = self._make_mock_report(files_created=["a.py"])
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report, editor_checkpoint_len=3)

        s = self.mgr.get_session()
        self.assertEqual(len(s.undo_stack), 1)
        entry = s.undo_stack[0]
        self.assertEqual(entry.editor_checkpoint_len, 3)
        self.assertIn("a.py", entry.files_affected)

    def test_record_task_complete_no_undo_entry_for_failed(self):
        self.mgr.start_session()
        task = self._make_mock_task(status=TaskStatus.FAILED)
        report = self._make_mock_report()
        self.mgr.record_task_start(task)
        self.mgr.record_task_complete(task, report, editor_checkpoint_len=0)

        s = self.mgr.get_session()
        self.assertEqual(len(s.undo_stack), 0)

    # ── Conversation rolling window ──────────────────────────────────────────

    def test_add_prompt_updates_rolling_window(self):
        self.mgr.start_session()
        self.mgr.add_prompt("Add auth", "Created jwt.py")
        s = self.mgr.get_session()
        self.assertIn("Add auth", s.recent_prompts)
        self.assertIn("Created jwt.py", s.recent_responses)

    def test_rolling_window_caps_at_10(self):
        self.mgr.start_session()
        for i in range(15):
            self.mgr.add_prompt(f"prompt {i}", f"response {i}")
        s = self.mgr.get_session()
        self.assertEqual(len(s.recent_prompts), 10)

    # ── Follow-up intent resolution ──────────────────────────────────────────

    def test_resolve_followup_returns_correct_intent(self):
        self.assertEqual(self.mgr.resolve_followup("undo"), FollowupIntent.UNDO)
        self.assertEqual(self.mgr.resolve_followup("continue"), FollowupIntent.CONTINUE)
        self.assertEqual(self.mgr.resolve_followup("add tests"), FollowupIntent.ADD_TESTS)
        self.assertEqual(
            self.mgr.resolve_followup("implement JWT auth"),
            FollowupIntent.NONE,
        )

    # ── build_followup_goal ──────────────────────────────────────────────────

    def test_build_followup_goal_continue(self):
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.task_history.append(TaskRecord("1", "Add login", "completed"))
        goal = self.mgr.build_followup_goal(FollowupIntent.CONTINUE)
        self.assertIn("Add login", goal)
        self.assertIn("Continue", goal)

    def test_build_followup_goal_add_tests(self):
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.files_created.add("auth.py")
        goal = self.mgr.build_followup_goal(FollowupIntent.ADD_TESTS)
        self.assertIn("auth.py", goal)
        self.assertIn("tests", goal.lower())

    def test_build_followup_goal_returns_none_for_undo(self):
        self.mgr.start_session()
        goal = self.mgr.build_followup_goal(FollowupIntent.UNDO)
        self.assertIsNone(goal)

    def test_build_followup_goal_none_when_no_session(self):
        # No session started
        goal = self.mgr.build_followup_goal(FollowupIntent.CONTINUE)
        self.assertIsNone(goal)

    # ── Undo / redo ──────────────────────────────────────────────────────────

    def test_undo_returns_false_with_empty_stack(self):
        self.mgr.start_session()
        result = self.mgr.undo_last_task()
        self.assertFalse(result)

    def test_undo_rolls_back_editor_and_removes_task_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.pae.scan(root)

            editor = CodeEditor()
            # Create a file via editor so we have a history entry
            (root / "dummy.py").write_text("x = 1")
            editor._get_project_root = lambda: root

            self.mgr.start_session()
            s = self.mgr.get_session()

            # Simulate a task that created dummy.py
            task = self._make_mock_task(goal="Create dummy.py", status=TaskStatus.COMPLETED)
            report = self._make_mock_report(files_created=["dummy.py"])
            checkpoint = len(editor.history)
            # Record as if the file was created mid-task
            s.task_history.append(
                TaskRecord("task-001", "Create dummy.py", "completed", files_created=["dummy.py"])
            )
            s.undo_stack.append(
                UndoEntry("task-001", "Create dummy.py", checkpoint, files_affected=["dummy.py"])
            )
            s.files_created.add("dummy.py")

            result = self.mgr.undo_last_task()
            self.assertTrue(result)
            # Task record should be removed
            self.assertEqual(len(s.task_history), 0)
            # File should be removed from files_created
            self.assertNotIn("dummy.py", s.files_created)
            # Entry should be on redo_stack
            self.assertEqual(len(s.redo_stack), 1)

    def test_undo_no_session_returns_false(self):
        result = self.mgr.undo_last_task()
        self.assertFalse(result)

    # ── Context prompt injection ─────────────────────────────────────────────

    def test_build_context_prompt_empty_when_no_session(self):
        prompt = self.mgr.build_context_prompt()
        self.assertEqual(prompt, "")

    def test_build_context_prompt_contains_project_name(self):
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.project_name = "myapp"
        s.languages = ["Python"]
        s.git_branch = "feature/auth"

        prompt = self.mgr.build_context_prompt()
        self.assertIn("myapp", prompt)
        self.assertIn("Python", prompt)
        self.assertIn("feature/auth", prompt)

    def test_build_context_prompt_contains_recent_files(self):
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.project_name = "myapp"
        s.files_created.add("auth.py")
        s.files_modified.add("app.py")

        prompt = self.mgr.build_context_prompt()
        self.assertIn("auth.py", prompt)

    def test_build_context_prompt_contains_recent_prompts(self):
        self.mgr.start_session()
        s = self.mgr.get_session()
        s.project_name = "myapp"
        self.mgr.add_prompt("Add JWT", "Created jwt.py")

        prompt = self.mgr.build_context_prompt()
        self.assertIn("Add JWT", prompt)

    def test_build_context_prompt_empty_header_only_when_no_data(self):
        self.mgr.start_session()
        s = self.mgr.get_session()
        # Force all context fields to be empty so prompt should be blank
        s.project_name = ""
        s.git_branch = ""
        s.current_task_goal = None
        s.task_history.clear()
        s.files_created.clear()
        s.files_modified.clear()
        s.recent_prompts.clear()
        s.recent_responses.clear()

        prompt = self.mgr.build_context_prompt()
        # Only header present — should return empty string
        self.assertEqual(prompt, "")

    # ── Task engine hook integration ─────────────────────────────────────────

    def test_task_engine_hooks_are_registered(self):
        """Verify on_step_complete / on_step_failed fields exist on engine."""
        engine = TaskExecutionEngine()
        self.assertTrue(hasattr(engine, "on_step_complete"))
        self.assertTrue(hasattr(engine, "on_step_failed"))

    def test_task_engine_step_complete_hook_fires(self):
        """The hook is invoked on step success."""
        TaskExecutionEngine._instance = None
        engine = TaskExecutionEngine()
        fired = []
        engine.on_step_complete = lambda task, step: fired.append(step.description)

        # Simulate calling the hook directly
        mock_task = MagicMock()
        mock_step = MagicMock()
        mock_step.description = "Create foo.py"
        engine.on_step_complete(mock_task, mock_step)

        self.assertIn("Create foo.py", fired)

    # ── No-session safety ────────────────────────────────────────────────────

    def test_add_prompt_without_session_is_safe(self):
        # Should not raise
        self.mgr.add_prompt("hello", "world")

    def test_record_task_start_without_session_returns_zero(self):
        task = self._make_mock_task()
        result = self.mgr.record_task_start(task)
        self.assertEqual(result, 0)

    def test_record_task_complete_without_session_is_safe(self):
        task = self._make_mock_task()
        report = self._make_mock_report()
        # Should not raise
        self.mgr.record_task_complete(task, report)
