"""
Integration and unit tests for TaskExecutionEngine.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from nova.project.engine import ProjectAwarenessEngine
from nova.code.engine import CodeIntelligenceEngine
from nova.task.engine import TaskExecutionEngine
from nova.task.models import TaskStatus
from nova.edit.editor import CodeEditor


class TestTaskExecutionEngine(unittest.TestCase):
    def setUp(self):
        # Reset all singletons
        TaskExecutionEngine._instance = None
        CodeEditor._instance = None
        ProjectAwarenessEngine._instance = None
        CodeIntelligenceEngine._instance = None
        
        self.pae = ProjectAwarenessEngine()
        self.cie = CodeIntelligenceEngine()
        self.engine = TaskExecutionEngine()
        self.engine.active_tasks.clear()

    def _setup_project(self, root: Path):
        """Scaffold temporary project root and parse in PAE/CIE."""
        (root / ".git").mkdir(parents=True, exist_ok=True)
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (root / "pyproject.toml").write_text('[project]\nname = "testapp"\n')
        
        proj_ctx = self.pae.scan(root)
        self.cie._full_index(proj_ctx)
        self.pae.register_change_listener(
            self.cie._change_listener_factory(self.pae)
        )

    @patch("nova.browser.providers.chatgpt.ChatGPTProvider.execute_action")
    def test_create_task_ai_decomposition(self, mock_ai):
        mock_ai.return_value = json.dumps([
            {"description": "Setup main.py", "action_type": "create_file", "metadata": {"rel_path": "main.py"}},
            {"description": "Configure settings", "action_type": "create_file", "metadata": {"rel_path": "settings.py"}}
        ])
        
        task = self.engine.create_task("Build simple app")
        self.assertEqual(len(task.steps), 2)
        self.assertEqual(task.steps[0].action_type, "create_file")
        self.assertEqual(task.steps[0].metadata["rel_path"], "main.py")

    @patch("nova.browser.providers.chatgpt.ChatGPTProvider.execute_action")
    def test_execute_task_success_flow(self, mock_ai):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self._setup_project(root)
            
            # Setup AI plan and generated code
            mock_ai.side_effect = [
                # Plan decomposition
                json.dumps([
                    {"description": "Create db.py", "action_type": "create_file", "metadata": {"rel_path": "db.py"}},
                ]),
                # Code generation for db.py
                "DB_CONN = 'sqlite://'\n"
            ]
            
            task = self.engine.create_task("Setup sqlite database")
            self.assertEqual(task.status, TaskStatus.PENDING)
            
            # Execute
            self.engine.execute_task(task.id)
            
            # Wait for execution thread to finish
            timeout = 5.0
            start = time.time()
            while self.engine.get_task_status(task.id) == TaskStatus.RUNNING:
                time.sleep(0.1)
                if time.time() - start > timeout:
                    self.fail("Task execution timed out")
                    
            self.assertEqual(self.engine.get_task_status(task.id), TaskStatus.COMPLETED)
            self.assertTrue((root / "db.py").exists())
            self.assertEqual((root / "db.py").read_text(), "DB_CONN = 'sqlite://'")

    @patch("nova.browser.providers.chatgpt.ChatGPTProvider.execute_action")
    def test_execute_task_step_failure_and_rollback(self, mock_ai):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self._setup_project(root)
            
            # Step 1: Create a valid py file
            # Step 2: Create a file with broken syntax (should fail verification/compilation)
            mock_ai.side_effect = [
                # Plan decomposition
                json.dumps([
                    {"description": "Create utils.py", "action_type": "create_file", "metadata": {"rel_path": "utils.py"}},
                    {"description": "Create bad.py", "action_type": "create_file", "metadata": {"rel_path": "bad.py"}}
                ]),
                # Step 1 code (valid)
                "def success():\n    return True\n",
                # Step 2 code (broken syntax)
                "def bad(\n",
                # Step 2 retry 1 (broken)
                "def bad_retry_1(\n",
                # Step 2 retry 2 (broken)
                "def bad_retry_2(\n",
                # Step 2 retry 3 (broken)
                "def bad_retry_3(\n"
            ]
            
            task = self.engine.create_task("Generate codebase")
            
            # Execute
            self.engine.execute_task(task.id)
            
            # Wait for failure
            timeout = 5.0
            start = time.time()
            while self.engine.get_task_status(task.id) in (TaskStatus.RUNNING, TaskStatus.PENDING):
                time.sleep(0.1)
                if time.time() - start > timeout:
                    self.fail("Task execution timed out")
                    
            self.assertEqual(self.engine.get_task_status(task.id), TaskStatus.FAILED)
            
            # Step 1 (utils.py) should be successfully completed and present on disk
            self.assertTrue((root / "utils.py").exists())
            
            # Step 2 (bad.py) failed validation and MUST be rolled back (not present on disk)
            self.assertFalse((root / "bad.py").exists())
            
            # Audit log should show Step 2 rollback
            self.assertIn("Create bad.py", task.rollbacks_executed)

    @patch("nova.browser.providers.chatgpt.ChatGPTProvider.execute_action")
    def test_task_pause_resume_cancel(self, mock_ai):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self._setup_project(root)
            
            # Decompose into multiple dummy steps
            mock_ai.side_effect = [
                json.dumps([
                    {"description": "Step A", "action_type": "generic", "metadata": {"rel_path": "a.py"}},
                    {"description": "Step B", "action_type": "generic", "metadata": {"rel_path": "b.py"}},
                    {"description": "Step C", "action_type": "generic", "metadata": {"rel_path": "c.py"}}
                ]),
                # Code content calls
                "a = 1", "b = 2", "c = 3"
            ]
            
            task = self.engine.create_task("Multi-step task")
            
            # Run
            self.engine.execute_task(task.id)
            
            # Pause immediately
            self.engine.pause_task(task.id)
            self.assertEqual(self.engine.get_task_status(task.id), TaskStatus.PAUSED)
            
            # Resume
            self.engine.resume_task(task.id)
            self.assertEqual(self.engine.get_task_status(task.id), TaskStatus.RUNNING)
            
            # Cancel
            self.engine.cancel_task(task.id)
            self.assertEqual(self.engine.get_task_status(task.id), TaskStatus.CANCELLED)
