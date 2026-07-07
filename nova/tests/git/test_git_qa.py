"""
nova.tests.git.test_git_qa
~~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive QA test suite verifying all 15 items for the Git Intelligence Engine.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from nova.git import get_git_engine, GitIntelligenceEngine
from nova.git.models import GitRepoStatus, CommitInfo
from nova.core.memory import get_working_memory, reset_working_memory
from nova.session import get_dev_session_manager


class TestGitQA(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for a local Git repository sandbox
        self.temp_dir = tempfile.mkdtemp()
        self.sandbox_path = Path(self.temp_dir).resolve()

        # Initialize real local git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "QA Tester"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "qa@nova.ai"], cwd=self.temp_dir, capture_output=True, check=True)

        # Clear GIE singleton state and re-initialize targeting sandbox
        GitIntelligenceEngine._instance = None
        self.engine = GitIntelligenceEngine()
        self.engine._cached_root = self.sandbox_path
        self.engine._cached_remote_url = None
        self.engine._cached_default_branch = None

        # Standard callback allowing actions
        self.confirm_val = True
        self.engine.confirm_callback = lambda msg: self.confirm_val

        # Reset process singletons
        reset_working_memory()
        self.dsm = get_dev_session_manager()
        self.dsm._session = None

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        GitIntelligenceEngine._instance = None
        reset_working_memory()

    # ═════════════════════════════════════════════════════════════════════════
    # 1. Repository detection
    # ═════════════════════════════════════════════════════════════════════════
    def test_01_repository_root_detection(self):
        """Verify engine detects correct repository root path."""
        root = self.engine.get_repo_root()
        self.assertEqual(root, self.sandbox_path)

    # ═════════════════════════════════════════════════════════════════════════
    # 2. Branch detection
    # ═════════════════════════════════════════════════════════════════════════
    def test_02_current_branch_detection(self):
        """Verify engine extracts current branch name from .git HEAD reference."""
        status = self.engine.get_status()
        self.assertEqual(status.current_branch, "main")

    # ═════════════════════════════════════════════════════════════════════════
    # 3. Repository status
    # ═════════════════════════════════════════════════════════════════════════
    def test_03_structured_repository_status(self):
        """Verify repository status snapshot is clean initially."""
        status = self.engine.get_status()
        self.assertTrue(status.is_clean)
        self.assertFalse(status.merge_in_progress)
        self.assertFalse(status.rebase_in_progress)

    # ═════════════════════════════════════════════════════════════════════════
    # 4. Modified file detection
    # ═════════════════════════════════════════════════════════════════════════
    def test_04_modified_files_detected(self):
        """Verify tracked files that are modified are listed in status modified_files."""
        file_path = self.sandbox_path / "hello.py"
        file_path.write_text("print('hello')", encoding="utf-8")
        
        # Stage and commit first
        self.engine.stage_files(["hello.py"])
        self.engine.create_commit("Initial commit")
        
        # Modify file and adjust utime to bypass racy Git
        time.sleep(0.1)
        file_path.write_text("print('modified hello')", encoding="utf-8")
        st = os.stat(file_path)
        os.utime(file_path, (st.st_atime, st.st_mtime + 2.0))

        status = self.engine.get_status()
        self.assertEqual(status.modified_files, ["hello.py"])

    # ═════════════════════════════════════════════════════════════════════════
    # 5. Untracked file detection
    # ═════════════════════════════════════════════════════════════════════════
    def test_05_untracked_files_detected(self):
        """Verify newly created untracked files are listed in status untracked_files."""
        file_path = self.sandbox_path / "untracked.py"
        file_path.write_text("print('untracked')", encoding="utf-8")

        status = self.engine.get_status()
        self.assertEqual(status.untracked_files, ["untracked.py"])

    # ═════════════════════════════════════════════════════════════════════════
    # 6. Staging files
    # ═════════════════════════════════════════════════════════════════════════
    def test_06_staging_files_workflow(self):
        """Verify staging untracked files puts them in staged status list."""
        file_path = self.sandbox_path / "staged.py"
        file_path.write_text("print('staged')", encoding="utf-8")

        self.engine.stage_files(["staged.py"])
        status = self.engine.get_status()
        self.assertEqual(status.staged_files, ["staged.py"])
        self.assertEqual(status.untracked_files, [])

    # ═════════════════════════════════════════════════════════════════════════
    # 7. Unstaging files
    # ═════════════════════════════════════════════════════════════════════════
    def test_07_unstaging_files_workflow(self):
        """Verify unstaging files moves them from staged back to untracked list."""
        file_path = self.sandbox_path / "test.py"
        file_path.write_text("content", encoding="utf-8")

        self.engine.stage_files(["test.py"])
        self.engine.unstage_files(["test.py"])
        status = self.engine.get_status()
        self.assertEqual(status.staged_files, [])
        self.assertEqual(status.untracked_files, ["test.py"])

    # ═════════════════════════════════════════════════════════════════════════
    # 8. Commit creation
    # ═════════════════════════════════════════════════════════════════════════
    def test_08_commit_creation_increases_history(self):
        """Verify commit creation succeeds and returns valid short commit hash."""
        (self.sandbox_path / "doc.txt").write_text("docs", encoding="utf-8")
        self.engine.stage_files(["doc.txt"])
        
        commit_hash = self.engine.create_commit("Add docs")
        self.assertIsNotNone(commit_hash)
        self.assertNotEqual(commit_hash, "unknown")
        
        history = self.engine.view_history(limit=5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].message, "Add docs")

    # ═════════════════════════════════════════════════════════════════════════
    # 9. AI-generated commit messages
    # ═════════════════════════════════════════════════════════════════════════
    @patch("nova.git.engine.ChatGPTProvider.execute_action")
    def test_09_ai_generate_commit_message(self, mock_ai_execute):
        """Verify GIE builds Conventional Commit prompts and cleans output wrappers."""
        mock_ai_execute.return_value = "```\nfeat: commit text\n```"
        (self.sandbox_path / "c.txt").write_text("changes", encoding="utf-8")
        self.engine.stage_files(["c.txt"])

        commit_msg = self.engine.ai_generate_commit_message()
        self.assertEqual(commit_msg, "feat: commit text")
        mock_ai_execute.assert_called_once()

    # ═════════════════════════════════════════════════════════════════════════
    # 10. Branch creation and switching
    # ═════════════════════════════════════════════════════════════════════════
    def test_10_branch_creation_and_switching(self):
        """Verify checkout can create a branch and switch current branch ref."""
        (self.sandbox_path / "doc.txt").write_text("docs", encoding="utf-8")
        self.engine.stage_files(["doc.txt"])
        self.engine.create_commit("Initial commit")

        self.engine.checkout_branch("test-branch", create=True)
        self.assertEqual(self.engine.get_status().current_branch, "test-branch")

    # ═════════════════════════════════════════════════════════════════════════
    # 11. Diff generation
    # ═════════════════════════════════════════════════════════════════════════
    def test_11_diff_generation_patch(self):
        """Verify get_diff returns patch lines for staged modification."""
        (self.sandbox_path / "hello.py").write_text("print('hello')", encoding="utf-8")
        self.engine.stage_files(["hello.py"])
        self.engine.create_commit("Initial commit")

        time.sleep(0.1)
        (self.sandbox_path / "hello.py").write_text("print('diff content')", encoding="utf-8")
        st = os.stat(self.sandbox_path / "hello.py")
        os.utime(self.sandbox_path / "hello.py", (st.st_atime, st.st_mtime + 2.0))

        diff = self.engine.get_diff()
        self.assertIn("diff --git a/hello.py b/hello.py", diff)
        self.assertIn("-print('hello')", diff)
        self.assertIn("+print('diff content')", diff)

    # ═════════════════════════════════════════════════════════════════════════
    # 12. Commit history retrieval
    # ═════════════════════════════════════════════════════════════════════════
    def test_12_commit_history_mapping(self):
        """Verify commit history logs return CommitInfo instances."""
        (self.sandbox_path / "init.txt").write_text("init", encoding="utf-8")
        self.engine.stage_files(["init.txt"])
        self.engine.create_commit("commit A")

        history = self.engine.view_history(limit=10)
        self.assertEqual(len(history), 1)
        self.assertIsInstance(history[0], CommitInfo)
        self.assertEqual(history[0].message, "commit A")

    # ═════════════════════════════════════════════════════════════════════════
    # 13. WorkingMemory synchronization
    # ═════════════════════════════════════════════════════════════════════════
    def test_13_working_memory_synchronization(self):
        """Verify Git variables propagate into process shared WorkingMemory."""
        (self.sandbox_path / "staged.txt").write_text("staged content", encoding="utf-8")
        (self.sandbox_path / "modified.txt").write_text("modified content", encoding="utf-8")
        self.engine.stage_files(["staged.txt"])

        self.engine.get_status()
        wm = get_working_memory()
        
        self.assertEqual(wm.get("current_branch"), "main")
        self.assertEqual(wm.get("staged_files"), ["staged.txt"])
        self.assertEqual(wm.get("modified_files"), [])
        self.assertEqual(wm.get("git_status"), "dirty")

    # ═════════════════════════════════════════════════════════════════════════
    # 14. Development Session synchronization
    # ═════════════════════════════════════════════════════════════════════════
    def test_14_development_session_synchronization(self):
        """Verify Git branch updates flow directly into active DSM session state."""
        self.dsm.start_session()
        # We need a commit to checkout/create a branch
        (self.sandbox_path / "init.txt").write_text("init", encoding="utf-8")
        self.engine.stage_files(["init.txt"])
        self.engine.create_commit("Initial commit")

        # Checkout new branch
        self.engine.checkout_branch("qa-sync-branch", create=True)
        self.assertEqual(self.dsm.get_session().git_branch, "qa-sync-branch")

    # ═════════════════════════════════════════════════════════════════════════
    # 15. Existing Nova functionality remains unaffected (Regression)
    # ═════════════════════════════════════════════════════════════════════════
    def test_15_regression_safety_on_working_memory(self):
        """Verify WorkingMemory clears, updates, and validates cleanly."""
        wm = get_working_memory()
        wm.set("project_name", "GIE_Validation")
        self.assertEqual(wm.get("project_name"), "GIE_Validation")


if __name__ == "__main__":
    unittest.main()
