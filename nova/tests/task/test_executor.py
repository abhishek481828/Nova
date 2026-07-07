"""
Unit tests for step execution.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from nova.task.executor import StepExecutor

class TestStepExecutor(unittest.TestCase):
    def test_is_destructive_action(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            executor = StepExecutor(root)
            
            # File deletion is destructive
            is_dest, _ = executor.is_destructive_action("delete_file", {"rel_path": "a.py"})
            self.assertTrue(is_dest)
            
            # Config file overwrite is destructive
            is_dest, _ = executor.is_destructive_action("update_file", {"rel_path": "config.json"})
            # Doesn't exist yet, so not destructive
            self.assertFalse(is_dest)
            
            # Create config.json
            (root / "config.json").write_text("{}", encoding="utf-8")
            is_dest, _ = executor.is_destructive_action("update_file", {"rel_path": "config.json"})
            # Now it exists, so overwrite is destructive
            self.assertTrue(is_dest)

    @patch("nova.edit.editor.CodeEditor.create_file")
    @patch("nova.browser.providers.chatgpt.ChatGPTProvider.execute_action")
    def test_execute_create_file(self, mock_ai, mock_create):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            executor = StepExecutor(root)
            
            mock_ai.return_value = "def handle():\n    pass\n"
            mock_create.return_value = MagicMock(success=True)
            
            ok, created, modified, err = executor.execute_step(
                "Create controller",
                "create_file",
                {"rel_path": "controller.py"}
            )
            
            self.assertTrue(ok)
            self.assertEqual(created, ["controller.py"])
            mock_create.assert_called_once_with("controller.py", "def handle():\n    pass")

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_execute_shell_command(self, mock_run):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            executor = StepExecutor(root)
            
            mock_run.return_value = (0, "Done", "")
            ok, created, modified, err = executor.execute_step(
                "Install dependency",
                "run_command",
                {"command": "pip install requests"}
            )
            
            self.assertTrue(ok)
            mock_run.assert_called_once_with("pip install requests", require_confirmation=False, cwd=str(root))
