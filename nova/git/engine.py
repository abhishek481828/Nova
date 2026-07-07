"""
nova.git.engine
~~~~~~~~~~~~~~~
GitIntelligenceEngine — provides thread-safe Git repository awareness,
safety-guarded actions, AI commit/diff intelligence, and session/memory synchronization.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from nova.git.models import CommitInfo, GitRepoStatus
from nova.project.engine import ProjectAwarenessEngine
from nova.session import get_dev_session_manager
from nova.core.memory import get_working_memory
from nova.browser.chatgpt_manager import ChatGPTManager
from nova.browser.providers.chatgpt import ChatGPTProvider

logger = logging.getLogger("nova.git.engine")


class GitIntelligenceEngine:
    """
    Thread-safe singleton for Git repository awareness and intelligence.
    """

    _instance: Optional["GitIntelligenceEngine"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "GitIntelligenceEngine":
        with cls._instance_lock:
            if cls._instance is None:
                obj = super().__new__(cls)
                obj._initialised = False
                cls._instance = obj
            return cls._instance

    def __init__(self, confirm_callback: Optional[Callable[[str], bool]] = None) -> None:
        if self._initialised:
            if confirm_callback is not None:
                self.confirm_callback = confirm_callback
            return
        self.confirm_callback = confirm_callback
        self._lock = threading.RLock()
        self._cached_root: Optional[Path] = None
        self._cached_remote_url: Optional[str] = None
        self._cached_default_branch: Optional[str] = None
        self._initialised = True

    # ── Safety checks ──────────────────────────────────────────────────────────

    def _require_confirmation(self, message: str) -> bool:
        """
        Prompt for confirmation via callback, logging safety warnings.
        If the callback returns False, raises a ValueError.
        If no callback exists, raises a ValueError to prevent destructive actions.
        """
        if self.confirm_callback:
            logger.info("[Git Safety] Requesting confirmation for: %s", message)
            if not self.confirm_callback(message):
                raise ValueError(f"Safety Guard: User rejected action: '{message}'")
            return True

        # Fail-safe: raise if no confirmation path is registered in production
        logger.warning("[Git Safety Warning] Destructive action blocked: %s", message)
        raise ValueError(
            f"Git Safety Block: A destructive operation '{message}' was requested "
            "but no confirmation callback is registered."
        )

    # ── Repository Root Resolution ──────────────────────────────────────────────

    def get_repo_root(self) -> Path:
        """
        Resolve the repository root. Reuses ProjectAwarenessEngine context
        to avoid redundant git subprocess lookups.
        """
        with self._lock:
            if self._cached_root is not None:
                return self._cached_root

            # Fallback to PAE
            try:
                pae = ProjectAwarenessEngine()
                ctx = pae.get_context()
                if ctx and ctx.root:
                    self._cached_root = ctx.root
                    return ctx.root
            except Exception:
                pass

            # System fallback to directory check
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=os.getcwd(),
                    timeout=3,
                )
                root = Path(result.stdout.strip()).resolve()
                self._cached_root = root
                return root
            except Exception:
                # Use current working directory if not a git repository
                return Path(os.getcwd()).resolve()

    # ── Git command runner ──────────────────────────────────────────────────────

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> str:
        """Executes a git subcommand safely and returns trimmed stdout."""
        root = cwd or self.get_repo_root()
        logger.debug("[Git Command] git %s", " ".join(args))
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(root),
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            return result.stdout.rstrip()
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() or e.stdout.strip() or str(e)
            logger.error("[Git Error] Command failed 'git %s': %s", " ".join(args), err_msg)
            raise ValueError(f"Git command failed: {err_msg}") from e

    # ── Status and Awareness ────────────────────────────────────────────────────

    def get_status(self) -> GitRepoStatus:
        """
        Scan repository files and returns a structured GitRepoStatus snapshot.
        """
        with self._lock:
            root = self.get_repo_root()
            root_str = str(root)

            # 1. Branch name (Optimized: read .git/HEAD directly first to support fresh repos without HEAD commit)
            branch = "detached"
            git_dir = root / ".git"
            if git_dir.exists():
                try:
                    head_path = git_dir / "HEAD"
                    if head_path.exists():
                        head_content = head_path.read_text(encoding="utf-8").strip()
                        m = re.match(r"^ref: refs/heads/(.+)$", head_content)
                        if m:
                            branch = m.group(1)
                except Exception as e:
                    logger.debug("Failed to read .git/HEAD directly: %s", e)

            if branch == "detached":
                try:
                    branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
                except Exception:
                    pass

            # 2. Remote URL (Cached)
            if self._cached_remote_url is None:
                try:
                    self._cached_remote_url = self._run_git(["config", "--get", "remote.origin.url"])
                except Exception:
                    self._cached_remote_url = ""

            # 3. Default branch name (Cached)
            if self._cached_default_branch is None:
                try:
                    ref = self._run_git(["symbolic-ref", "refs/remotes/origin/HEAD"])
                    self._cached_default_branch = ref.split("/")[-1]
                except Exception:
                    # Check common default branch names
                    try:
                        branches = self._run_git(["branch", "-r"])
                        if "origin/main" in branches:
                            self._cached_default_branch = "main"
                        elif "origin/master" in branches:
                            self._cached_default_branch = "master"
                        else:
                            self._cached_default_branch = "main"
                    except Exception:
                        self._cached_default_branch = "main"

            # 4. Modified, staged, untracked lists
            modified: List[str] = []
            staged: List[str] = []
            untracked: List[str] = []

            status_raw = ""
            try:
                status_raw = self._run_git(["status", "--porcelain"])
            except Exception as e:
                logger.debug("Failed to run git status --porcelain: %s", e)

            if status_raw:
                for line in status_raw.splitlines():
                    if len(line) < 3:
                        continue
                    xy = line[:2]
                    file_path = line[2:].strip()
                    # Resolve renamed files "src -> dst"
                    if " -> " in file_path:
                        file_path = file_path.split(" -> ")[-1].strip()

                    x, y = xy[0], xy[1]

                    # Staged changes index indicators
                    if x in ("M", "A", "D", "R", "C"):
                        staged.append(file_path)
                    # Unstaged modifications in working tree
                    if y in ("M", "D"):
                        modified.append(file_path)
                    # Untracked files
                    if x == "?" and y == "?":
                        untracked.append(file_path)

            # 5. Check merge / rebase locks
            merge_in_progress = (git_dir / "MERGE_HEAD").exists() if git_dir.exists() else False
            rebase_in_progress = (
                (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()
            ) if git_dir.exists() else False

            status = GitRepoStatus(
                repository_root=root_str,
                current_branch=branch,
                remote_url=self._cached_remote_url or None,
                default_branch=self._cached_default_branch,
                is_clean=(not status_raw),
                modified_files=sorted(list(set(modified))),
                staged_files=sorted(list(set(staged))),
                untracked_files=sorted(list(set(untracked))),
                merge_in_progress=merge_in_progress,
                rebase_in_progress=rebase_in_progress,
            )

            self._sync_with_session_and_memory(status)
            return status

    # ── Commit Intelligence Operations ──────────────────────────────────────────

    def stage_files(self, paths: List[str]) -> None:
        """Stage targeted paths into git index."""
        if not paths:
            return
        # Staging specific files is not destructive
        self._run_git(["add"] + paths)
        logger.info("[Git Engine] Staged %d file(s)", len(paths))
        self.get_status()  # trigger refresh & sync

    def unstage_files(self, paths: List[str]) -> None:
        """Remove targeted paths from git index (unstaged changes remain in files)."""
        if not paths:
            return
        # Unstaging is not destructive to files
        try:
            self._run_git(["restore", "--staged"] + paths)
        except Exception:
            # Fallback to older git reset HEAD
            self._run_git(["reset", "HEAD", "--"] + paths)
        logger.info("[Git Engine] Unstaged %d file(s)", len(paths))
        self.get_status()

    def create_commit(self, message: str) -> str:
        """Create a commit with the staged changes and message."""
        if not message.strip():
            raise ValueError("Commit message cannot be empty")
        output = self._run_git(["commit", "-m", message])
        logger.info("[Git Engine] Created commit: %s", message.split("\n")[0])
        # Retrieve short hash from output
        m = re.search(r"\[.+ ([0-9a-f]+)\]", output)
        commit_hash = m.group(1) if m else "unknown"
        self.get_status()
        return commit_hash

    def view_history(self, limit: int = 10) -> List[CommitInfo]:
        """Return history log as parsed CommitInfo dataclass list."""
        raw_log = ""
        try:
            raw_log = self._run_git(
                ["log", f"--max-count={limit}", "--pretty=format:%H%x1f%an%x1f%ct%x1f%s"]
            )
        except Exception as e:
            logger.debug("Failed to fetch commit log: %s", e)

        history: List[CommitInfo] = []
        if not raw_log:
            return history

        for line in raw_log.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 4:
                continue
            history.append(
                CommitInfo(
                    commit_hash=parts[0],
                    author=parts[1],
                    timestamp=float(parts[2]),
                    message=parts[3],
                )
            )
        return history

    def get_diff(self, staged_only: bool = False, paths: Optional[List[str]] = None) -> str:
        """Return raw diff patch output."""
        args = ["diff"]
        if staged_only:
            args.append("--cached")
        if paths:
            args += ["--"] + paths
        try:
            return self._run_git(args)
        except Exception as e:
            logger.debug("Failed to retrieve git diff: %s", e)
            return ""

    def compare_commits(self, commit1: str, commit2: str) -> str:
        """Return differences between two commits."""
        return self._run_git(["diff", f"{commit1}..{commit2}"])

    def restore_files(self, paths: List[str]) -> None:
        """Discard uncommitted modifications inside paths."""
        if not paths:
            return
        # Safety: Discarding file edits is destructive!
        self._require_confirmation(
            f"Discard all uncommitted local modifications inside: {', '.join(paths)}"
        )
        try:
            self._run_git(["restore"] + paths)
        except Exception:
            self._run_git(["checkout", "--"] + paths)
        logger.info("[Git Engine] Restored modifications in %d file(s)", len(paths))
        self.get_status()

    def checkout_branch(self, name: str, create: bool = False) -> None:
        """Switch to local branch name, optionally creating it."""
        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(name)
        self._run_git(args)
        logger.info("[Git Engine] Checked out branch: %s", name)
        self.get_status()

    def delete_branch(self, name: str, force: bool = False) -> None:
        """Safely delete branch locally."""
        # Safety: Deleting a branch is potentially destructive
        self._require_confirmation(
            f"Delete local branch '{name}' (force={force})"
        )
        flag = "-D" if force else "-d"
        self._run_git(["branch", flag, name])
        logger.info("[Git Engine] Deleted local branch: %s", name)
        self.get_status()

    # ── Non-safe Destructive Commands (Confirmed execution only) ────────────────

    def hard_reset(self, target: str = "HEAD") -> None:
        """Force discard staged/unstaged changes and aligns files with target commit."""
        self._require_confirmation(
            f"Hard reset files to match target commit state: '{target}' (Deletes uncommitted code)"
        )
        self._run_git(["reset", "--hard", target])
        logger.info("[Git Engine] Hard reset complete to target: %s", target)
        self.get_status()

    def clean_workspace(self, force: bool = True) -> None:
        """Purge untracked files and directories from the repository root."""
        self._require_confirmation("Purge all untracked files and folders in workspace (clean -fd)")
        args = ["clean", "-f", "-d"]
        self._run_git(args)
        logger.info("[Git Engine] Workspace cleaned successfully.")
        self.get_status()

    # ── AI Provider Integration ─────────────────────────────────────────────────

    def _query_ai(self, prompt: str) -> str:
        """Help method to route prompts to active AI provider."""
        provider = getattr(ChatGPTManager, "_active_provider", None) or ChatGPTProvider
        raw = provider.execute_action("ask", prompt)
        clean = raw.strip()
        # Remove surrounding markdown wrappers if generated by assistant
        if clean.startswith("```"):
            lines = clean.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean = "\n".join(lines).strip()
        return clean

    def ai_generate_commit_message(self) -> str:
        """Inspects staged changes diff and uses the AI Provider to compose a commit message."""
        diff = self.get_diff(staged_only=True)
        if not diff.strip():
            raise ValueError("No staged changes available to generate a commit message")

        prompt = (
            "You are a Git commit message assistant. Please analyze the following Git diff and "
            "generate a high-quality commit message following the Conventional Commits specification "
            "(e.g., feat: ..., fix: ..., refactor: ..., docs: ...). Keep the subject line under 50 "
            "characters, follow it with a blank line and a concise bulleted description of the changes. "
            "Output ONLY the commit message itself. Do not include markdown wraps (like ```), header text, or filler.\n\n"
            f"Diff:\n{diff}"
        )
        return self._query_ai(prompt)

    def ai_summarize_diff(self, paths: Optional[List[str]] = None) -> str:
        """Generate summary explanations for local changes diff."""
        diff = self.get_diff(staged_only=False, paths=paths)
        if not diff.strip():
            return "No changes detected in workspace."

        prompt = (
            "Please provide a clear and concise summary of the changes in the following Git diff. "
            "Highlight the key modifications and their impact.\n\n"
            f"Diff:\n{diff}"
        )
        return self._query_ai(prompt)

    def ai_explain_conflict(self, file_content: str) -> str:
        """Provide detailed insights and resolution suggestion for conflict block indicators."""
        prompt = (
            "Please explain the following merge conflict files and contents. Identify which sections conflict "
            "and suggest a logical resolution strategy.\n\n"
            f"Conflict data:\n{file_content}"
        )
        return self._query_ai(prompt)

    def ai_suggest_commit_groupings(self) -> str:
        """Analyzes modified files and recommends staging sets for logical commits."""
        status = self.get_status()
        all_files = status.modified_files + status.untracked_files
        if not all_files:
            return "No changes detected to group."

        diff = self.get_diff()
        prompt = (
            "Given the following list of modified files and their diffs, suggest how they should be grouped "
            "into logical, independent commits. For each suggested commit, list the files and a brief reason.\n\n"
            f"Files: {', '.join(all_files)}\n\n"
            f"Diff / File list:\n{diff}"
        )
        return self._query_ai(prompt)

    # ── Session & Memory Synchronization ────────────────────────────────────────

    def _sync_with_session_and_memory(self, status: GitRepoStatus) -> None:
        """Mirror current status parameters into DSM session state and process WorkingMemory."""
        # 1. Update DevelopmentSession
        try:
            dsm = get_dev_session_manager()
            s = dsm.get_session()
            if s:
                s.git_branch = status.current_branch
        except Exception as e:
            logger.debug("[Git Engine] Could not sync with session manager: %s", e)

        # 2. Update Shared WorkingMemory
        try:
            wm = get_working_memory()
            wm.set("current_branch", status.current_branch)
            wm.set("git_status", "clean" if status.is_clean else "dirty")
            wm.set("staged_files", status.staged_files)
            wm.set("modified_files", status.modified_files)

            # Expose last commit hash
            try:
                last_hash = self._run_git(["rev-parse", "--short", "HEAD"])
                wm.set("last_commit", last_hash)
            except Exception:
                wm.set("last_commit", None)

        except Exception as e:
            logger.debug("[Git Engine] Could not mirror to WorkingMemory: %s", e)
