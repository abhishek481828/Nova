"""
nova.tests.git.test_git_engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit and integration tests for the Git Intelligence Engine.
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


class TestGitIntelligenceEngine(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for a local Git repository sandbox
        self.temp_dir = tempfile.mkdtemp()
        self.sandbox_path = Path(self.temp_dir).resolve()

        # Initialize real local git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Nova Tester"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@nova.ai"], cwd=self.temp_dir, capture_output=True, check=True)

        # Instantiate GIE manually mapping to our sandbox root
        # Clean singleton cache
        GitIntelligenceEngine._instance = None
        self.engine = GitIntelligenceEngine()
        self.engine._cached_root = self.sandbox_path

        # Set a mock confirm callback
        self.confirm_val = True
        self.engine.confirm_callback = lambda msg: self.confirm_val

        # Reset process singletons
        reset_working_memory()
        get_dev_session_manager()._session = None

    def tearDown(self):
        # Cleanup directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        GitIntelligenceEngine._instance = None
        reset_working_memory()

    # ── 1. Status Awareness Tests ──────────────────────────────────────────────

    def test_repo_status_fresh_repo(self):
        status = self.engine.get_status()
        self.assertEqual(status.current_branch, "main")
        self.assertTrue(status.is_clean)
        self.assertEqual(status.modified_files, [])
        self.assertEqual(status.staged_files, [])
        self.assertEqual(status.untracked_files, [])

    def test_repo_status_with_file_changes(self):
        # 1. Untracked file
        file1 = self.sandbox_path / "file1.txt"
        file1.write_text("Hello World", encoding="utf-8")

        status1 = self.engine.get_status()
        self.assertFalse(status1.is_clean)
        self.assertEqual(status1.untracked_files, ["file1.txt"])

        # 2. Stage file
        self.engine.stage_files(["file1.txt"])
        status2 = self.engine.get_status()
        self.assertEqual(status2.staged_files, ["file1.txt"])
        self.assertEqual(status2.untracked_files, [])

        # 3. Create initial commit
        self.engine.create_commit("Initial commit")
        status3 = self.engine.get_status()
        self.assertTrue(status3.is_clean)

        # 4. Modify tracked file (touch utime to avoid time resolution collisions)
        file1.write_text("Modified Hello", encoding="utf-8")
        st = os.stat(file1)
        os.utime(file1, (st.st_atime, st.st_mtime + 2.0))
        status4 = self.engine.get_status()
        print("DEBUG status4:", status4)
        print("DEBUG porcelain:", self.engine._run_git(["status", "--porcelain"]))
        self.assertEqual(status4.modified_files, ["file1.txt"])

    # ── 2. Staging & Unstaging Tests ───────────────────────────────────────────

    def test_stage_and_unstage_files(self):
        file1 = self.sandbox_path / "a.txt"
        file1.write_text("content", encoding="utf-8")
        
        self.engine.stage_files(["a.txt"])
        self.assertEqual(self.engine.get_status().staged_files, ["a.txt"])
        
        self.engine.unstage_files(["a.txt"])
        status = self.engine.get_status()
        self.assertEqual(status.staged_files, [])
        self.assertEqual(status.untracked_files, ["a.txt"])

    # ── 3. Branching Operations ────────────────────────────────────────────────

    def test_checkout_and_branch_deletion(self):
        # Initial commit needed to be able to create branches in git
        (self.sandbox_path / "init.txt").write_text("init", encoding="utf-8")
        self.engine.stage_files(["init.txt"])
        self.engine.create_commit("Initial")

        # Create feature branch
        self.engine.checkout_branch("feature-xyz", create=True)
        self.assertEqual(self.engine.get_status().current_branch, "feature-xyz")

        # Switch back to main
        self.engine.checkout_branch("main")
        self.assertEqual(self.engine.get_status().current_branch, "main")

        # Delete feature branch safely
        self.engine.delete_branch("feature-xyz")
        # Running branch list command to assert deletion
        branches = self.engine._run_git(["branch"])
        self.assertNotIn("feature-xyz", branches)

    # ── 4. Safety Guard Confirmations ──────────────────────────────────────────

    def test_safety_guarded_destructive_action_accepted(self):
        # Create commit first so HEAD revision exists
        (self.sandbox_path / "init.txt").write_text("init", encoding="utf-8")
        self.engine.stage_files(["init.txt"])
        self.engine.create_commit("Initial")

        self.confirm_val = True
        # Hard reset shouldn't raise if callback returns True
        self.engine.hard_reset()

    def test_safety_guarded_destructive_action_rejected(self):
        # Create commit first so HEAD revision exists
        (self.sandbox_path / "init.txt").write_text("init", encoding="utf-8")
        self.engine.stage_files(["init.txt"])
        self.engine.create_commit("Initial")

        self.confirm_val = False
        # Should raise ValueError if user rejects
        with self.assertRaises(ValueError) as ctx:
            self.engine.hard_reset()
        self.assertIn("Safety Guard: User rejected action", str(ctx.exception))

    def test_safety_guarded_destructive_action_missing_callback(self):
        # Create commit first so HEAD revision exists
        (self.sandbox_path / "init.txt").write_text("init", encoding="utf-8")
        self.engine.stage_files(["init.txt"])
        self.engine.create_commit("Initial")

        self.engine.confirm_callback = None
        # Should raise ValueError indicating missing callback
        with self.assertRaises(ValueError) as ctx:
            self.engine.hard_reset()
        self.assertIn("Git Safety Block: A destructive operation", str(ctx.exception))

    # ── 5. AI Prompt & Generation Integration ──────────────────────────────────

    @patch("nova.git.engine.ChatGPTProvider.execute_action")
    def test_ai_commit_message_generation(self, mock_ai_execute):
        mock_ai_execute.return_value = "```\nfeat: add file1\n\n- Created file1.txt\n```"
        
        # Modify and stage changes
        (self.sandbox_path / "file1.txt").write_text("new change", encoding="utf-8")
        self.engine.stage_files(["file1.txt"])

        commit_msg = self.engine.ai_generate_commit_message()
        self.assertEqual(commit_msg, "feat: add file1\n\n- Created file1.txt")
        # Verify provider called with matching prompt containing git diff
        mock_ai_execute.assert_called_once()
        self.assertIn("generate a high-quality commit message", mock_ai_execute.call_args[0][1])

    @patch("nova.git.engine.ChatGPTProvider.execute_action")
    def test_ai_diff_summarization(self, mock_ai_execute):
        # Create and commit file first
        (self.sandbox_path / "file1.txt").write_text("initial value", encoding="utf-8")
        self.engine.stage_files(["file1.txt"])
        self.engine.create_commit("Initial commit")

        mock_ai_execute.return_value = "Summed changes."
        
        # Modify the file so a real diff exists
        file_path = self.sandbox_path / "file1.txt"
        file_path.write_text("new change", encoding="utf-8")
        st = os.stat(file_path)
        os.utime(file_path, (st.st_atime, st.st_mtime + 2.0))
        
        summary = self.engine.ai_summarize_diff()
        self.assertEqual(summary, "Summed changes.")
        self.assertIn("summary of the changes", mock_ai_execute.call_args[0][1])

    # ── 6. State Mirroring & WorkingMemory Sync ───────────────────────────────

    def test_working_memory_sync_triggers(self):
        # Fresh status updates WorkingMemory
        self.engine.get_status()
        
        wm = get_working_memory()
        self.assertEqual(wm.get("current_branch"), "main")
        self.assertEqual(wm.get("git_status"), "clean")
        self.assertEqual(wm.get("staged_files"), [])
        self.assertEqual(wm.get("modified_files"), [])

        # Create modifications
        (self.sandbox_path / "changed.txt").write_text("stuff", encoding="utf-8")
        self.engine.get_status()

        self.assertEqual(wm.get("git_status"), "dirty")
        self.assertEqual(wm.get("modified_files"), [])
        self.assertEqual(wm.get("staged_files"), [])

        # Stage and check again
        self.engine.stage_files(["changed.txt"])
        self.assertEqual(wm.get("git_status"), "dirty")
        self.assertEqual(wm.get("staged_files"), ["changed.txt"])


if __name__ == "__main__":
    unittest.main()
