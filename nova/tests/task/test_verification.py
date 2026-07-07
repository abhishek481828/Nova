"""
Unit tests for step verification.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nova.task.verification import StepVerifier

class TestStepVerifier(unittest.TestCase):
    def test_verify_files_exist(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            verifier = StepVerifier(root)
            
            # Check non-existent file
            ok, errors = verifier.verify_files_exist(["missing.py"])
            self.assertFalse(ok)
            self.assertEqual(len(errors), 1)
            
            # Create file
            (root / "present.py").write_text("print('hi')", encoding="utf-8")
            ok, errors = verifier.verify_files_exist(["present.py"])
            self.assertTrue(ok)

    def test_verify_syntax_python(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            verifier = StepVerifier(root)
            
            # Valid syntax
            (root / "good.py").write_text("def test():\n    pass\n", encoding="utf-8")
            ok, errors = verifier.verify_syntax(["good.py"])
            self.assertTrue(ok)
            
            # Invalid syntax
            (root / "bad.py").write_text("def test(\n", encoding="utf-8")
            ok, errors = verifier.verify_syntax(["bad.py"])
            self.assertFalse(ok)
            self.assertGreater(len(errors), 0)

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_run_tests(self, mock_run):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            verifier = StepVerifier(root)
            
            # Successful test run (code 0)
            mock_run.return_value = (0, "all passed", "")
            ok, errors = verifier.run_tests(test_command="pytest")
            self.assertTrue(ok)
            
            # Failing test run (code 1)
            mock_run.return_value = (1, "", "1 failed")
            ok, errors = verifier.run_tests(test_command="pytest")
            self.assertFalse(ok)
            self.assertIn("failed", errors[0])
