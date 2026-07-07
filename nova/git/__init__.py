"""
nova.git
~~~~~~~~
Git Intelligence Engine — Safe repository management and Git status awareness.
"""
from __future__ import annotations

from nova.git.engine import GitIntelligenceEngine


def get_git_engine() -> GitIntelligenceEngine:
    """Return the process-wide shared GitIntelligenceEngine instance."""
    return GitIntelligenceEngine()


__all__ = [
    "GitIntelligenceEngine",
    "get_git_engine",
]
