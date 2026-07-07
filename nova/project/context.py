"""
nova.project.context
~~~~~~~~~~~~~~~~~~~~
ProjectContext — the immutable, shared snapshot of the active project.
All Nova components read from this object; nothing writes to it directly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class LanguageInfo:
    """Detected programming language with statistics."""
    name: str            # e.g. "Python", "TypeScript"
    extension: str       # e.g. ".py", ".ts"
    file_count: int      # number of source files
    primary: bool        # True if this is the dominant language


@dataclass(frozen=True)
class FileNode:
    """Lightweight metadata for a single indexed file."""
    path: str            # relative path from project root
    extension: str
    size_bytes: int
    mtime: float         # last modified timestamp
    imports: tuple       # top-level import names (regex-extracted)


@dataclass
class ProjectContext:
    """
    Complete in-memory representation of the detected project.

    This object is produced by ProjectAwarenessEngine.scan() and is the
    single public API surface that other Nova modules consume. It is
    intentionally a mutable dataclass so the watcher can update it
    incrementally without producing a full rescan overhead.
    """
    root: Path
    name: str

    # Language & framework
    languages: List[LanguageInfo] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)

    # Dependencies aggregated from all manifests
    dependencies: Dict[str, str] = field(default_factory=dict)
    dev_dependencies: Dict[str, str] = field(default_factory=dict)

    # File index: relative_path → FileNode
    file_index: Dict[str, FileNode] = field(default_factory=dict)

    # Git
    is_git_repo: bool = False
    git_branch: Optional[str] = None
    git_remote: Optional[str] = None

    # Scan metadata
    last_scanned: float = field(default_factory=time.time)
    scan_duration_s: float = 0.0
    total_files: int = 0
    total_size_bytes: int = 0

    # Arbitrary extra metadata from manifests
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Convenience helpers                                                  #
    # ------------------------------------------------------------------ #

    @property
    def primary_language(self) -> Optional[str]:
        """Returns the name of the dominant language, or None."""
        for lang in self.languages:
            if lang.primary:
                return lang.name
        return self.languages[0].name if self.languages else None

    @property
    def all_language_names(self) -> List[str]:
        return [lang.name for lang in self.languages]

    @property
    def summary(self) -> str:
        """Human-readable one-liner for use in prompts/TTS."""
        langs = ", ".join(self.all_language_names) or "unknown"
        fw = ", ".join(self.frameworks) if self.frameworks else "no framework detected"
        git = f"git:{self.git_branch}" if self.is_git_repo and self.git_branch else "no git"
        return (
            f"Project '{self.name}' at {self.root} | "
            f"Languages: {langs} | Frameworks: {fw} | {git} | "
            f"{self.total_files} files"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict (for JSON caching)."""
        return {
            "root": str(self.root),
            "name": self.name,
            "languages": [
                {
                    "name": l.name,
                    "extension": l.extension,
                    "file_count": l.file_count,
                    "primary": l.primary,
                }
                for l in self.languages
            ],
            "frameworks": self.frameworks,
            "dependencies": self.dependencies,
            "dev_dependencies": self.dev_dependencies,
            "is_git_repo": self.is_git_repo,
            "git_branch": self.git_branch,
            "git_remote": self.git_remote,
            "last_scanned": self.last_scanned,
            "scan_duration_s": self.scan_duration_s,
            "total_files": self.total_files,
            "total_size_bytes": self.total_size_bytes,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectContext":
        """Deserialise from a cached dict."""
        langs = [
            LanguageInfo(
                name=l["name"],
                extension=l["extension"],
                file_count=l["file_count"],
                primary=l["primary"],
            )
            for l in data.get("languages", [])
        ]
        ctx = cls(
            root=Path(data["root"]),
            name=data["name"],
            languages=langs,
            frameworks=data.get("frameworks", []),
            dependencies=data.get("dependencies", {}),
            dev_dependencies=data.get("dev_dependencies", {}),
            is_git_repo=data.get("is_git_repo", False),
            git_branch=data.get("git_branch"),
            git_remote=data.get("git_remote"),
            last_scanned=data.get("last_scanned", time.time()),
            scan_duration_s=data.get("scan_duration_s", 0.0),
            total_files=data.get("total_files", 0),
            total_size_bytes=data.get("total_size_bytes", 0),
            metadata=data.get("metadata", {}),
        )
        return ctx
