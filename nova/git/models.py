"""
nova.git.models
~~~~~~~~~~~~~~~
Data models representing Git repository state snapshots and commits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GitRepoStatus:
    """
    Represents a full read-only snapshot of the active Git repository status.
    """
    repository_root: str
    current_branch: str = "detached"
    remote_url: Optional[str] = None
    default_branch: str = "main"
    is_clean: bool = True
    modified_files: List[str] = field(default_factory=list)
    staged_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    merge_in_progress: bool = False
    rebase_in_progress: bool = False

    @property
    def summary(self) -> str:
        """Return a single-line summary description of the repository state."""
        status_desc = "clean" if self.is_clean else "dirty"
        changes = (
            f"staged={len(self.staged_files)} modified={len(self.modified_files)} "
            f"untracked={len(self.untracked_files)}"
        )
        extra = []
        if self.merge_in_progress:
            extra.append("MERGING")
        if self.rebase_in_progress:
            extra.append("REBASING")
        extra_str = f" [{', '.join(extra)}]" if extra else ""

        return f"Branch: {self.current_branch} ({status_desc}) | {changes}{extra_str}"


@dataclass
class CommitInfo:
    """
    Represents a single commit record parsed from the Git history log.
    """
    commit_hash: str
    author: str
    timestamp: float
    message: str
