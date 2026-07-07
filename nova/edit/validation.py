"""
nova.edit.validation
~~~~~~~~~~~~~~~~~~~~
Pre-save validation for source files.

Python:  stdlib ast.parse() — exact, zero external deps.
TypeScript/JS: heuristic brace/paren balance check — no npm needed.
Generic: always passes (we can't validate arbitrary file types).
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ValidationResult:
    """Outcome of a pre-save validation check."""
    is_valid:  bool
    errors:    List[str] = field(default_factory=list)
    warnings:  List[str] = field(default_factory=list)
    language:  str = "unknown"

    @classmethod
    def ok(cls, language: str = "unknown") -> "ValidationResult":
        return cls(is_valid=True, language=language)

    @classmethod
    def fail(cls, error: str, language: str = "unknown") -> "ValidationResult":
        return cls(is_valid=False, errors=[error], language=language)


# ── Python ────────────────────────────────────────────────────────────────────

def validate_python(content: str, filename: str = "<string>") -> ValidationResult:
    """
    Validate Python source using ast.parse().
    Returns a ValidationResult with the SyntaxError message if invalid.
    """
    try:
        ast.parse(content, filename=filename)
        return ValidationResult.ok(language="Python")
    except SyntaxError as e:
        msg = f"SyntaxError at line {e.lineno}: {e.msg}"
        return ValidationResult.fail(msg, language="Python")
    except Exception as e:
        return ValidationResult.fail(str(e), language="Python")


# ── TypeScript / JavaScript ───────────────────────────────────────────────────

def validate_typescript(content: str, filename: str = "<string>") -> ValidationResult:
    """
    Heuristic validator for TypeScript/JavaScript.
    Checks:
      - Balanced braces { }
      - Balanced parentheses ( )
      - Balanced brackets [ ]
      - No unclosed multi-line comment /* ... */
    This catches the most common editing accidents without requiring a JS AST.
    """
    warnings: List[str] = []

    # Strip string literals to avoid false positives from braces in strings
    stripped = _strip_strings_and_comments(content)

    opens  = {"(": ")", "{": "}", "[": "]"}
    closes = {v: k for k, v in opens.items()}
    stack: List[str] = []

    for i, ch in enumerate(stripped):
        if ch in opens:
            stack.append(ch)
        elif ch in closes:
            expected = closes[ch]
            if not stack:
                line = content[:i].count("\n") + 1
                return ValidationResult.fail(
                    f"Unexpected '{ch}' at line {line} (no matching '{expected}')",
                    language="TypeScript",
                )
            top = stack.pop()
            if top != expected:
                line = content[:i].count("\n") + 1
                return ValidationResult.fail(
                    f"Mismatched '{ch}' at line {line} (expected closing for '{top}')",
                    language="TypeScript",
                )

    if stack:
        return ValidationResult.fail(
            f"Unclosed '{stack[-1]}' — missing closing bracket",
            language="TypeScript",
        )

    # Check for unclosed block comments
    if "/*" in content:
        opens_count  = content.count("/*")
        closes_count = content.count("*/")
        if opens_count != closes_count:
            warnings.append("Possibly unclosed block comment /* ... */")

    return ValidationResult(is_valid=True, warnings=warnings, language="TypeScript")


def _strip_strings_and_comments(content: str) -> str:
    """
    Replace string literal contents and comments with spaces so brace
    counting is not confused by braces inside strings.
    Handles: "...", '...', `...`, // ..., /* ... */
    """
    # Block comments
    result = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group()), content, flags=re.DOTALL)
    # Line comments
    result = re.sub(r"//[^\n]*", lambda m: " " * len(m.group()), result)
    # Template literals (backtick strings, simplified)
    result = re.sub(r"`[^`]*`", lambda m: " " * len(m.group()), result, flags=re.DOTALL)
    # Double-quoted strings
    result = re.sub(r'"(?:[^"\\]|\\.)*"', lambda m: " " * len(m.group()), result)
    # Single-quoted strings
    result = re.sub(r"'(?:[^'\\]|\\.)*'", lambda m: " " * len(m.group()), result)
    return result


# ── Generic fallback ─────────────────────────────────────────────────────────

def validate_generic(content: str, filename: str = "<string>") -> ValidationResult:
    """Always returns valid — used for file types without a specific validator."""
    return ValidationResult.ok(language="generic")


# ── Dispatcher ───────────────────────────────────────────────────────────────

_PYTHON_EXTS = {".py", ".pyi"}
_TS_EXTS     = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def validate_file(rel_path: str, content: str) -> ValidationResult:
    """
    Validate *content* using the appropriate validator for the file type.
    Dispatches by file extension.
    """
    ext = Path(rel_path).suffix.lower()
    if ext in _PYTHON_EXTS:
        return validate_python(content, filename=rel_path)
    elif ext in _TS_EXTS:
        return validate_typescript(content, filename=rel_path)
    else:
        return validate_generic(content, filename=rel_path)
