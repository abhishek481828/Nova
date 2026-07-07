"""
nova.edit.python_editor
~~~~~~~~~~~~~~~~~~~~~~~
AST-based editing utilities for Python (.py) files.
"""
from __future__ import annotations

import ast
import logging
from typing import List, Optional

logger = logging.getLogger("nova.edit.python_editor")

class PythonRenameTransformer(ast.NodeTransformer):
    """
    AST transformer to rename references to a symbol.
    """
    def __init__(self, old_name: str, new_name: str) -> None:
        self.old_name = old_name
        self.new_name = new_name

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id == self.old_name:
            return ast.copy_location(ast.Name(id=self.new_name, ctx=node.ctx), node)
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if node.name == self.old_name:
            node.name = self.new_name
        # Also visit body
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        if node.name == self.old_name:
            node.name = self.new_name
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        if node.name == self.old_name:
            node.name = self.new_name
        return self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        if node.arg == self.old_name:
            node.arg = self.new_name
        return self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        if node.attr == self.old_name:
            node.attr = self.new_name
        return self.generic_visit(node)


def rename_symbol_in_source(content: str, old_name: str, new_name: str) -> str:
    """
    Rename all occurrences of old_name to new_name in Python source via AST.
    """
    try:
        tree = ast.parse(content)
        transformer = PythonRenameTransformer(old_name, new_name)
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)
    except Exception as e:
        logger.warning(f"AST-based rename failed: {e}. Falling back to word boundary replacement.")
        import re
        # Fallback to word boundaries
        return re.sub(rf"\b{old_name}\b", new_name, content)


def remove_function(content: str, func_name: str) -> str:
    """
    Remove a function by name from Python source code while preserving other structure.
    Uses AST to locate line numbers of the function (and its decorators), then removes those lines.
    """
    try:
        tree = ast.parse(content)
        lines = content.splitlines(keepends=True)
        
        target_node = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                target_node = node
                break
                
        if not target_node:
            raise ValueError(f"Function {func_name} not found.")

        # Determine start line including decorators
        start_line = target_node.lineno
        if target_node.decorator_list:
            start_line = min(d.lineno for d in target_node.decorator_list)

        end_line = target_node.end_lineno if hasattr(target_node, 'end_lineno') and target_node.end_lineno else target_node.lineno
        
        # 1-indexed to 0-indexed slice
        # Keep everything except the range [start_line - 1, end_line]
        new_lines = lines[:start_line - 1] + lines[end_line:]
        return "".join(new_lines)
    except Exception as e:
        logger.warning(f"AST-based function removal failed: {e}")
        raise


def insert_function(content: str, func_source: str, after_name: Optional[str] = None) -> str:
    """
    Insert a function into the Python source code.
    If after_name is specified, inserts immediately after that function/class.
    Otherwise, appends to the end of the file.
    """
    lines = content.splitlines(keepends=True)
    if not after_name:
        # Append with clean spacing
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n\n" + func_source + "\n")
        return "".join(lines)

    try:
        tree = ast.parse(content)
        insert_line = None
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == after_name:
                insert_line = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else node.lineno
                break
                
        if insert_line is None:
            raise ValueError(f"Target node '{after_name}' not found for insertion.")

        # Insert after the end line of the target node
        func_source_formatted = "\n\n" + func_source.strip() + "\n"
        new_lines = lines[:insert_line] + [func_source_formatted] + lines[insert_line:]
        return "".join(new_lines)
    except Exception as e:
        logger.warning(f"AST-based function insertion failed: {e}. Appending to end.")
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n\n" + func_source + "\n")
        return "".join(lines)


def insert_import(content: str, import_stmt: str) -> str:
    """
    Insert an import statement into Python source code.
    Tries to place it after existing imports. If no imports exist, places at the top.
    """
    lines = content.splitlines(keepends=True)
    try:
        tree = ast.parse(content)
        last_import_line = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                end_line = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else node.lineno
                if end_line > last_import_line:
                    last_import_line = end_line
        
        stmt = import_stmt.strip() + "\n"
        if last_import_line > 0:
            # Insert after the last import line
            new_lines = lines[:last_import_line] + [stmt] + lines[last_import_line:]
        else:
            # Place at top, skipping docstring if present
            docstring_end = 0
            if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
                docstring_end = tree.body[0].end_lineno if hasattr(tree.body[0], 'end_lineno') and tree.body[0].end_lineno else tree.body[0].lineno
            
            if docstring_end > 0:
                new_lines = lines[:docstring_end] + ["\n" + stmt] + lines[docstring_end:]
            else:
                new_lines = [stmt] + lines
                
        return "".join(new_lines)
    except Exception as e:
        logger.warning(f"AST-based import insertion failed: {e}. Prepending to top.")
        return import_stmt.strip() + "\n" + content
