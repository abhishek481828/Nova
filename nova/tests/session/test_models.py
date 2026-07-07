"""
Unit tests for nova.session.models — DevelopmentSession, TaskRecord, UndoEntry.
"""
import time
import unittest
from collections import deque
from pathlib import Path

from nova.session.models import (
    DevelopmentSession,
    FollowupIntent,
    TaskRecord,
    UndoEntry,
)


class TestFollowupIntent(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(FollowupIntent.NONE.value, "none")
        self.assertEqual(FollowupIntent.UNDO.value, "undo")
        self.assertEqual(FollowupIntent.REDO.value, "redo")
        self.assertEqual(FollowupIntent.CONTINUE.value, "continue")
        self.assertEqual(FollowupIntent.ADD_TESTS.value, "add_tests")
        self.assertEqual(FollowupIntent.DOCUMENT.value, "document")


class TestTaskRecord(unittest.TestCase):
    def test_defaults(self):
        rec = TaskRecord(task_id="t1", goal="Add auth", status="completed")
        self.assertEqual(rec.task_id, "t1")
        self.assertEqual(rec.goal, "Add auth")
        self.assertEqual(rec.status, "completed")
        self.assertEqual(rec.files_created, [])
        self.assertEqual(rec.files_modified, [])
        self.assertTrue(rec.validation_passed)
        self.assertGreater(rec.finished_at, 0)

    def test_custom_fields(self):
        rec = TaskRecord(
            task_id="t2",
            goal="Create login page",
            status="failed",
            steps_executed=3,
            steps_failed=1,
            files_created=["login.py"],
            validation_passed=False,
            duration_s=1.5,
        )
        self.assertEqual(rec.steps_executed, 3)
        self.assertEqual(rec.steps_failed, 1)
        self.assertFalse(rec.validation_passed)
        self.assertIn("login.py", rec.files_created)


class TestUndoEntry(unittest.TestCase):
    def test_defaults(self):
        entry = UndoEntry(
            task_id="t1",
            task_goal="Add auth",
            editor_checkpoint_len=5,
        )
        self.assertEqual(entry.editor_checkpoint_len, 5)
        self.assertEqual(entry.files_affected, [])
        self.assertGreater(entry.timestamp, 0)

    def test_files_affected(self):
        entry = UndoEntry(
            task_id="t1",
            task_goal="Create",
            editor_checkpoint_len=3,
            files_affected=["a.py", "b.py"],
        )
        self.assertEqual(len(entry.files_affected), 2)


class TestDevelopmentSession(unittest.TestCase):
    def _make_session(self) -> DevelopmentSession:
        return DevelopmentSession(
            project_name="myapp",
            project_root=Path("/tmp/myapp"),
            languages=["Python"],
            frameworks=["FastAPI"],
            git_branch="main",
        )

    def test_defaults(self):
        s = DevelopmentSession()
        self.assertIsNotNone(s.session_id)
        self.assertIsNone(s.project_root)
        self.assertEqual(s.languages, [])
        self.assertEqual(s.files_created, set())
        self.assertIsNone(s.last_task_record)
        self.assertEqual(s.all_changed_files, [])

    def test_last_task_record(self):
        s = self._make_session()
        self.assertIsNone(s.last_task_record)
        rec = TaskRecord(task_id="1", goal="Test", status="completed")
        s.task_history.append(rec)
        self.assertEqual(s.last_task_record.goal, "Test")

    def test_all_changed_files(self):
        s = self._make_session()
        s.files_created.add("a.py")
        s.files_modified.add("b.py")
        s.files_deleted.add("c.py")
        changed = s.all_changed_files
        self.assertIn("a.py", changed)
        self.assertIn("b.py", changed)
        self.assertIn("c.py", changed)
        # No duplicates
        self.assertEqual(len(changed), len(set(changed)))

    def test_duration(self):
        s = self._make_session()
        time.sleep(0.05)
        self.assertGreater(s.duration_s, 0)

    def test_tasks_completed_and_failed_count(self):
        s = self._make_session()
        s.task_history.append(TaskRecord(task_id="1", goal="G1", status="completed"))
        s.task_history.append(TaskRecord(task_id="2", goal="G2", status="completed"))
        s.task_history.append(TaskRecord(task_id="3", goal="G3", status="failed"))
        self.assertEqual(s.tasks_completed, 2)
        self.assertEqual(s.tasks_failed, 1)

    def test_recent_prompts_maxlen(self):
        s = DevelopmentSession()
        for i in range(15):
            s.recent_prompts.append(f"prompt {i}")
        self.assertEqual(len(s.recent_prompts), 10)
        self.assertEqual(s.recent_prompts[-1], "prompt 14")

    def test_undo_redo_stacks_are_lists(self):
        s = DevelopmentSession()
        self.assertIsInstance(s.undo_stack, list)
        self.assertIsInstance(s.redo_stack, list)
