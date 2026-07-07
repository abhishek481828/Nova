"""
Integration tests for CodeEditor service.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nova.edit.editor import CodeEditor
from nova.edit.operations import EditKind


class TestCodeEditor(unittest.TestCase):
    def setUp(self):
        # Reset the singleton and clear history before each test
        CodeEditor._instance = None
        self.editor = CodeEditor()
        self.editor.history.clear()

    @patch("nova.edit.editor.CodeEditor._get_project_root")
    def test_create_read_update_delete_flow(self, mock_root):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mock_root.return_value = root
            
            rel_path = "src/api.py"
            content = "def hello():\n    return 'world'\n"
            
            # Create file
            res = self.editor.create_file(rel_path, content)
            self.assertTrue(res.success)
            self.assertTrue((root / rel_path).exists())
            
            # Read file
            read_content = self.editor.read_file(rel_path)
            self.assertEqual(read_content, content)
            
            # Update file
            new_content = "def hello():\n    return 'new world'\n"
            res_update = self.editor.update_file(rel_path, new_content)
            self.assertTrue(res_update.success)
            self.assertEqual(self.editor.read_file(rel_path), new_content)
            self.assertIsNotNone(res_update.backup_path)
            
            # Delete file
            res_delete = self.editor.delete_file(rel_path)
            self.assertTrue(res_delete.success)
            self.assertFalse((root / rel_path).exists())

    @patch("nova.edit.editor.CodeEditor._get_project_root")
    def test_rollback_last_change(self, mock_root):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mock_root.return_value = root
            
            rel_path = "src/config.py"
            initial_content = "DEBUG = True\nPORT = 8000\n"
            
            self.editor.create_file(rel_path, initial_content)
            
            # Update content
            updated_content = "DEBUG = False\nPORT = 9000\n"
            self.editor.update_file(rel_path, updated_content)
            self.assertEqual(self.editor.read_file(rel_path), updated_content)
            
            # Rollback
            res_rollback = self.editor.rollback_last_change()
            self.assertTrue(res_rollback.success)
            self.assertEqual(self.editor.read_file(rel_path), initial_content)

    @patch("nova.edit.editor.CodeEditor._get_project_root")
    def test_rename_symbol(self, mock_root):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mock_root.return_value = root
            
            rel_path = "src/utils.py"
            content = "def calculate_sum(a, b):\n    return a + b\n"
            self.editor.create_file(rel_path, content)
            
            res = self.editor.rename_symbol(rel_path, "calculate_sum", "add_values")
            self.assertTrue(res.success)
            self.assertIn("def add_values(a, b):", self.editor.read_file(rel_path))

    @patch("nova.edit.editor.CodeEditor._get_project_root")
    def test_replace_function(self, mock_root):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mock_root.return_value = root
            
            rel_path = "src/math.py"
            content = (
                "def multiply(a, b):\n"
                "    return a * b\n"
                "\n"
                "def divide(a, b):\n"
                "    return a / b\n"
            )
            self.editor.create_file(rel_path, content)
            
            new_func = "def multiply(a, b):\n    print('multiplied!')\n    return a * b"
            res = self.editor.replace_function(rel_path, "multiply", new_func)
            self.assertTrue(res.success)
            
            updated_src = self.editor.read_file(rel_path)
            self.assertIn("print('multiplied!')", updated_src)
            self.assertIn("def divide(a, b):", updated_src)

    @patch("nova.edit.editor.CodeEditor._get_project_root")
    def test_invalid_syntax_rejected(self, mock_root):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mock_root.return_value = root
            
            rel_path = "src/bad.py"
            bad_content = "def broken(\n"
            
            res = self.editor.create_file(rel_path, bad_content)
            self.assertFalse(res.success)
            self.assertFalse((root / rel_path).exists())
            self.assertIn("Validation failed", res.message)
