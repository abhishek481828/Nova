"""
Integration tests verifying CodeEditor interaction with ProjectAwarenessEngine
and CodeIntelligenceEngine.
"""
import tempfile
import time
import unittest
from pathlib import Path

from nova.project.engine import ProjectAwarenessEngine
from nova.code.engine import CodeIntelligenceEngine
from nova.edit.editor import CodeEditor
from nova.code.context import CodeContext


class TestCodeEditorEngineIntegration(unittest.TestCase):
    def setUp(self):
        # Reset Singletons
        ProjectAwarenessEngine._instance = None
        CodeIntelligenceEngine._instance = None
        CodeEditor._instance = None
        
        self.pae = ProjectAwarenessEngine()
        self.cie = CodeIntelligenceEngine()
        self.editor = CodeEditor()

    def test_editor_updates_pae_and_cie_indices(self):
        """
        Verify that file edits via CodeEditor trigger updates in both
        ProjectAwarenessEngine and CodeIntelligenceEngine contexts.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            
            # Create a simple valid Python project
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
            (root / "pyproject.toml").write_text('[project]\nname = "testapp"\n')
            
            # Perform initial project scan
            self.pae.scan(root)
            proj_ctx = self.pae.get_context()
            self.assertIsNotNone(proj_ctx)
            
            # Start watcher/listeners
            self.cie._full_index(proj_ctx)
            self.pae.register_change_listener(
                self.cie._change_listener_factory(self.pae)
            )
            
            # Force CodeEditor to use this temp root
            with unittest.mock.patch.object(self.editor, "_get_project_root", return_value=root):
                
                # 1. Create a Python file
                rel_path = "math_utils.py"
                content = "def square(x):\n    return x * x\n"
                
                create_res = self.editor.create_file(rel_path, content)
                self.assertTrue(create_res.success)
                
                # Verify PAE has the new file in file_index
                proj_ctx = self.pae.get_context()
                self.assertIn(rel_path, proj_ctx.file_index)
                
                # Verify CIE has the new symbol "square"
                code_ctx = self.cie.get_context()
                self.assertIsNotNone(code_ctx)
                hits = code_ctx.find_symbol("square")
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0].file, rel_path)
                
                # 2. Update the Python file to add a new function "cube"
                updated_content = (
                    "def square(x):\n"
                    "    return x * x\n"
                    "\n"
                    "def cube(x):\n"
                    "    return x * x * x\n"
                )
                update_res = self.editor.update_file(rel_path, updated_content)
                self.assertTrue(update_res.success)
                
                # Verify CIE now has the new symbol "cube"
                code_ctx = self.cie.get_context()
                cube_hits = code_ctx.find_symbol("cube")
                self.assertEqual(len(cube_hits), 1)
                
                # 3. Rename a function: square -> square_val
                rename_res = self.editor.rename_symbol(rel_path, "square", "square_val")
                self.assertTrue(rename_res.success)
                
                # Verify "square" is gone, "square_val" is present
                code_ctx = self.cie.get_context()
                self.assertEqual(len(code_ctx.find_symbol("square")), 0)
                self.assertEqual(len(code_ctx.find_symbol("square_val")), 1)
                
                # 4. Rollback last change
                rollback_res = self.editor.rollback_last_change()
                self.assertTrue(rollback_res.success)
                
                # Verify "square" is back, "square_val" is gone
                code_ctx = self.cie.get_context()
                self.assertEqual(len(code_ctx.find_symbol("square")), 1)
                self.assertEqual(len(code_ctx.find_symbol("square_val")), 0)
                
                # 5. Delete file
                delete_res = self.editor.delete_file(rel_path)
                self.assertTrue(delete_res.success)
                
                # Verify file is removed from PAE and CIE
                proj_ctx = self.pae.get_context()
                self.assertNotIn(rel_path, proj_ctx.file_index)
                
                code_ctx = self.cie.get_context()
                self.assertEqual(len(code_ctx.find_symbol("square")), 0)
                self.assertEqual(len(code_ctx.find_symbol("cube")), 0)
