"""
nova.edit.typescript_editor
~~~~~~~~~~~~~~~~~~~~~~~~~~
Regex and brace-depth based editing utilities for JavaScript/TypeScript files.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("nova.edit.typescript_editor")

def rename_symbol_in_source(content: str, old_name: str, new_name: str) -> str:
    """
    Rename all occurrences of old_name to new_name in TS/JS source code.
    Uses regex with word boundary checking to avoid partial matches.
    """
    # Replace occurrences that match \b{old_name}\b
    return re.sub(rf"\b{old_name}\b", new_name, content)


def remove_function(content: str, func_name: str) -> str:
    """
    Remove a function by name from JS/TS source code using brace-depth tracking.
    Locates function keyword/declaration, tracks braces to find the body's end, and removes it.
    """
    # Pattern to find function or const arrow assignment
    # e.g., "function func_name(" or "const func_name = (" or "const func_name = async ("
    pattern = re.compile(
        rf"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+{func_name}\b|"
        rf"(?:export\s+)?(?:const|let|var)\s+{func_name}\s*="
    )
    
    match = pattern.search(content)
    if not match:
        raise ValueError(f"Function/Variable '{func_name}' not found in source.")

    start_pos = match.start()
    
    # Let's find the first opening brace '{' after start_pos
    brace_start = content.find("{", start_pos)
    if brace_start == -1:
        # Might be a single-line arrow function without braces or expression statement
        # Fallback: remove until the next semicolon
        semi = content.find(";", start_pos)
        if semi != -1:
            return content[:start_pos] + content[semi + 1:]
        # Or until the next newline
        nl = content.find("\n", start_pos)
        if nl != -1:
            return content[:start_pos] + content[nl + 1:]
        return content[:start_pos]

    # Walk from brace_start to find the matching closing brace
    depth = 0
    end_pos = -1
    for i in range(brace_start, len(content)):
        char = content[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end_pos = i + 1
                break
                
    if end_pos == -1:
        raise ValueError(f"Unbalanced braces in function '{func_name}'.")

    # Clean up trailing spaces or newlines
    rest = content[end_pos:]
    if rest.startswith(";"):
        rest = rest[1:]
    
    # Strip leading newlines/spaces from the rest
    return content[:start_pos].rstrip() + "\n" + rest.lstrip()


def insert_function(content: str, func_source: str, after_name: Optional[str] = None) -> str:
    """
    Insert a function into the TS/JS source code.
    If after_name is specified, attempts to find that function and inserts after its closing brace.
    Otherwise, appends to the end of the file.
    """
    if not after_name:
        lines = content.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n\n" + func_source + "\n")
        return "".join(lines)

    try:
        # Locate after_name function definition
        pattern = re.compile(
            rf"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+{after_name}\b|"
            rf"(?:export\s+)?(?:const|let|var)\s+{after_name}\s*="
        )
        match = pattern.search(content)
        if not match:
            raise ValueError(f"Function/Variable '{after_name}' not found.")

        brace_start = content.find("{", match.start())
        if brace_start == -1:
            # Fallback to semicolon
            semi = content.find(";", match.start())
            if semi != -1:
                insert_pos = semi + 1
            else:
                insert_pos = content.find("\n", match.start())
                if insert_pos == -1:
                    insert_pos = len(content)
        else:
            depth = 0
            insert_pos = -1
            for i in range(brace_start, len(content)):
                char = content[i]
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        insert_pos = i + 1
                        break
            if insert_pos == -1:
                raise ValueError("Mismatched braces in target function.")

        # Clean insert position
        rest = content[insert_pos:]
        if rest.startswith(";"):
            insert_pos += 1
            
        formatted_source = "\n\n" + func_source.strip() + "\n"
        return content[:insert_pos] + formatted_source + content[insert_pos:]
    except Exception as e:
        logger.warning(f"TS function insertion failed: {e}. Appending to end.")
        lines = content.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n\n" + func_source + "\n")
        return "".join(lines)


def insert_import(content: str, import_stmt: str) -> str:
    """
    Insert an import statement into TS/JS source code.
    Inserts after existing imports or at the very top.
    """
    lines = content.splitlines(keepends=True)
    last_import_index = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith("import ") or line.strip().startswith("require("):
            last_import_index = idx
            
    stmt = import_stmt.strip() + "\n"
    if last_import_index != -1:
        new_lines = lines[:last_import_index + 1] + [stmt] + lines[last_import_index + 1:]
    else:
        new_lines = [stmt] + lines
    return "".join(new_lines)
