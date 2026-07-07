"""
nova.edit.diff
~~~~~~~~~~~~~~
Unified diff generation using Python's stdlib difflib.
No external dependencies required.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import List


@dataclass
class DiffResult:
    """Result of a unified diff comparison."""
    diff_text:     str       # Full unified diff string
    lines_added:   int       # Number of added lines (+)
    lines_removed: int       # Number of removed lines (-)
    is_empty:      bool      # True if old == new (no changes)
    has_changes:   bool      # Alias for not is_empty

    def __str__(self) -> str:
        return self.diff_text


def generate_diff(
    old_content: str,
    new_content: str,
    filename: str = "file",
    context_lines: int = 3,
) -> DiffResult:
    """
    Generate a unified diff between *old_content* and *new_content*.

    Parameters
    ----------
    old_content :
        Original file content (before edit).
    new_content :
        Updated file content (after edit).
    filename :
        The file name to include in the diff header.
    context_lines :
        Number of context lines to include around each change (default 3).

    Returns
    -------
    DiffResult
        Contains the diff text and line-count statistics.
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff_lines: List[str] = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context_lines,
        )
    )

    diff_text = "".join(diff_lines)
    added   = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
    is_empty = (old_content == new_content)

    return DiffResult(
        diff_text=diff_text,
        lines_added=added,
        lines_removed=removed,
        is_empty=is_empty,
        has_changes=not is_empty,
    )


def apply_diff_preview(old_content: str, new_content: str, filename: str) -> str:
    """
    Return a coloured terminal-friendly diff string for TTS/display.
    Lines starting with + are prefixed with [ADD], - with [DEL].
    """
    result = generate_diff(old_content, new_content, filename)
    if result.is_empty:
        return "(no changes)"
    lines = []
    for line in result.diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            lines.append(line)
        elif line.startswith("+"):
            lines.append(f"[ADD] {line[1:]}")
        elif line.startswith("-"):
            lines.append(f"[DEL] {line[1:]}")
        else:
            lines.append(f"      {line}")
    return "\n".join(lines)
