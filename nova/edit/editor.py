"""
nova.edit.editor
~~~~~~~~~~~~~~~~
CodeEditor — the unified semantic editing service for Nova.
Integrates backup, validation, diff generation, history, and incremental index updates.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from nova.edit.backup import BackupManager
from nova.edit.diff import generate_diff
from nova.edit.operations import EditHistory, EditKind, EditOperation, EditResult
from nova.edit.validation import validate_file

logger = logging.getLogger("nova.edit.editor")

class CodeEditor:
    """
    Code editing service for Nova.
    Supports atomic mutations, backup & rollback, semantic code modification,
    syntactic validation, and triggers incremental index updates in Project
    and Code Intelligence Engines.
    """

    _instance: Optional["CodeEditor"] = None

    def __new__(cls) -> "CodeEditor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self.history = EditHistory()
        self._initialised = True

    # ── Helpers to retrieve project info ──────────────────────────

    def _get_project_root(self) -> Path:
        """Get the active project root from ProjectAwarenessEngine, or default to current cwd."""
        try:
            from nova.project.engine import ProjectAwarenessEngine
            pae = ProjectAwarenessEngine()
            ctx = pae.get_context()
            if ctx:
                return ctx.root
        except Exception:
            pass
        return Path.cwd()

    def _notify_engines(self, event_type: str, rel_path: str) -> None:
        """Trigger incremental index updates in PAE and CIE."""
        root = self._get_project_root()
        
        # 1. Update Project Awareness Engine context
        try:
            from nova.project.engine import ProjectAwarenessEngine
            from nova.project.indexer import update_index_for_file
            
            pae = ProjectAwarenessEngine()
            ctx = pae.get_context()
            if ctx:
                full_path = root / rel_path
                update_index_for_file(ctx.file_index, ctx.root, full_path)
                ctx.total_files = len(ctx.file_index)
                ctx.last_scanned = time.time()
                # Fan out to listeners (which will notify CIE)
                for listener in list(pae._change_listeners):
                    try:
                        listener(event_type, rel_path)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Failed to update project engine index: {e}")

        # 2. Safety fallback for Code Intelligence Engine if listeners failed
        try:
            from nova.code.engine import CodeIntelligenceEngine
            cie = CodeIntelligenceEngine()
            cie_ctx = cie.get_context()
            if cie_ctx:
                cie.on_file_change(event_type, rel_path, root)
        except Exception as e:
            logger.debug(f"Failed to update code intelligence engine index: {e}")

    # ── Public API: Read / Write ──────────────────────────────────

    def read_file(self, rel_path: str) -> str:
        """Read a file relative to the project root."""
        root = self._get_project_root()
        full_path = root / rel_path
        return full_path.read_text(encoding="utf-8", errors="replace")

    def create_file(self, rel_path: str, content: str) -> EditResult:
        """Create a new file with the given content."""
        t0 = time.perf_counter()
        root = self._get_project_root()
        full_path = root / rel_path
        
        if full_path.exists():
            return EditResult.fail(f"File already exists at: {rel_path}")

        # Validation
        val = validate_file(rel_path, content)
        if not val.is_valid:
            return EditResult.fail(f"Validation failed: {val.errors[0]}", metadata={"validation": val})

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            
            # Record operation
            op = EditOperation(
                kind=EditKind.CREATE,
                rel_path=rel_path,
                old_content=None,
                new_content=content,
            )
            self.history.push(op)
            
            # Update indexes
            self._notify_engines("added", rel_path)
            
            diff_res = generate_diff("", content, filename=rel_path)
            elapsed = time.perf_counter() - t0
            return EditResult.ok(
                message=f"Created file: {rel_path}",
                diff=diff_res.diff_text,
                duration_s=round(elapsed, 3),
            )
        except Exception as e:
            return EditResult.fail(f"Failed to create file: {e}")

    def update_file(self, rel_path: str, new_content: str) -> EditResult:
        """Atomically overwrite/update a file's content with backup and validation."""
        t0 = time.perf_counter()
        root = self._get_project_root()
        full_path = root / rel_path

        if not full_path.exists():
            return EditResult.fail(f"File does not exist: {rel_path}")

        # Validation
        val = validate_file(rel_path, new_content)
        if not val.is_valid:
            return EditResult.fail(f"Validation failed: {val.errors[0]}", metadata={"validation": val})

        try:
            old_content = full_path.read_text(encoding="utf-8", errors="replace")
            if old_content == new_content:
                return EditResult.ok(message="No changes made.", diff="", duration_s=0.0)

            # Backup
            bm = BackupManager(root)
            backup_file = bm.backup(rel_path)

            full_path.write_text(new_content, encoding="utf-8")

            # Record operation
            op = EditOperation(
                kind=EditKind.UPDATE,
                rel_path=rel_path,
                old_content=old_content,
                new_content=new_content,
            )
            self.history.push(op)

            # Update indexes
            self._notify_engines("modified", rel_path)

            diff_res = generate_diff(old_content, new_content, filename=rel_path)
            elapsed = time.perf_counter() - t0
            return EditResult.ok(
                message=f"Updated file: {rel_path}",
                diff=diff_res.diff_text,
                backup_path=str(backup_file) if backup_file else None,
                duration_s=round(elapsed, 3),
            )
        except Exception as e:
            return EditResult.fail(f"Failed to update file: {e}")

    def rename_file(self, old_rel: str, new_rel: str) -> EditResult:
        """Rename a file and update indexes accordingly."""
        t0 = time.perf_counter()
        root = self._get_project_root()
        old_full = root / old_rel
        new_full = root / new_rel

        if not old_full.exists():
            return EditResult.fail(f"Source file does not exist: {old_rel}")
        if new_full.exists():
            return EditResult.fail(f"Destination file already exists: {new_rel}")

        try:
            # Backup before rename (copy current to backup as old_rel)
            bm = BackupManager(root)
            backup_file = bm.backup(old_rel)

            content = old_full.read_text(encoding="utf-8", errors="replace")
            
            new_full.parent.mkdir(parents=True, exist_ok=True)
            old_full.rename(new_full)

            # Record operation
            op = EditOperation(
                kind=EditKind.RENAME_FILE,
                rel_path=old_rel,
                old_content=content,
                new_content=None,
                dest_rel_path=new_rel,
            )
            self.history.push(op)

            # Update indexes
            self._notify_engines("deleted", old_rel)
            self._notify_engines("added", new_rel)

            elapsed = time.perf_counter() - t0
            return EditResult.ok(
                message=f"Renamed {old_rel} to {new_rel}",
                backup_path=str(backup_file) if backup_file else None,
                duration_s=round(elapsed, 3),
            )
        except Exception as e:
            return EditResult.fail(f"Failed to rename file: {e}")

    def delete_file(self, rel_path: str) -> EditResult:
        """Delete a file with backup."""
        t0 = time.perf_counter()
        root = self._get_project_root()
        full_path = root / rel_path

        if not full_path.exists():
            return EditResult.fail(f"File does not exist: {rel_path}")

        try:
            # Backup
            bm = BackupManager(root)
            backup_file = bm.backup(rel_path)

            old_content = full_path.read_text(encoding="utf-8", errors="replace")
            full_path.unlink()

            # Record operation
            op = EditOperation(
                kind=EditKind.DELETE,
                rel_path=rel_path,
                old_content=old_content,
                new_content=None,
            )
            self.history.push(op)

            # Update indexes
            self._notify_engines("deleted", rel_path)

            elapsed = time.perf_counter() - t0
            return EditResult.ok(
                message=f"Deleted file: {rel_path}",
                backup_path=str(backup_file) if backup_file else None,
                duration_s=round(elapsed, 3),
            )
        except Exception as e:
            return EditResult.fail(f"Failed to delete file: {e}")

    def move_file(self, src_rel: str, dst_rel: str) -> EditResult:
        """Move a file from src_rel to dst_rel."""
        return self.rename_file(src_rel, dst_rel)

    # ── Public API: Semantic/Structured Edits ─────────────────────

    def rename_symbol(self, rel_path: str, old_name: str, new_name: str) -> EditResult:
        """Rename all occurrences of a symbol in the specified file."""
        try:
            content = self.read_file(rel_path)
            ext = Path(rel_path).suffix.lower()
            
            if ext in (".py", ".pyi"):
                from nova.edit.python_editor import rename_symbol_in_source
                new_content = rename_symbol_in_source(content, old_name, new_name)
            elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                from nova.edit.typescript_editor import rename_symbol_in_source
                new_content = rename_symbol_in_source(content, old_name, new_name)
            else:
                import re
                new_content = re.sub(rf"\b{old_name}\b", new_name, content)
                
            return self.update_file(rel_path, new_content)
        except Exception as e:
            return EditResult.fail(f"Failed to rename symbol: {e}")

    def insert_code(self, rel_path: str, code: str, after_line: int) -> EditResult:
        """Insert code block after a specific 1-indexed line number."""
        try:
            content = self.read_file(rel_path)
            lines = content.splitlines(keepends=True)
            if after_line < 0 or after_line > len(lines):
                return EditResult.fail(f"Invalid after_line number: {after_line}. File has {len(lines)} lines.")
            
            # Format insertion block
            block = code if code.endswith("\n") else code + "\n"
            new_lines = lines[:after_line] + [block] + lines[after_line:]
            return self.update_file(rel_path, "".join(new_lines))
        except Exception as e:
            return EditResult.fail(f"Failed to insert code: {e}")

    def replace_function(self, rel_path: str, func_name: str, new_func_source: str) -> EditResult:
        """Replace a function with a new implementation."""
        try:
            content = self.read_file(rel_path)
            ext = Path(rel_path).suffix.lower()
            
            # First remove the function
            if ext in (".py", ".pyi"):
                from nova.edit.python_editor import remove_function, insert_function
                removed_content = remove_function(content, func_name)
                # Now insert the new function in its place (or append)
                new_content = insert_function(removed_content, new_func_source)
            elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                from nova.edit.typescript_editor import remove_function, insert_function
                removed_content = remove_function(content, func_name)
                new_content = insert_function(removed_content, new_func_source)
            else:
                return EditResult.fail("Replace function is not supported for generic files. Use update_file.")
                
            return self.update_file(rel_path, new_content)
        except Exception as e:
            return EditResult.fail(f"Failed to replace function: {e}")

    def insert_import(self, rel_path: str, import_stmt: str) -> EditResult:
        """Insert an import statement into the file."""
        try:
            content = self.read_file(rel_path)
            ext = Path(rel_path).suffix.lower()
            
            if ext in (".py", ".pyi"):
                from nova.edit.python_editor import insert_import
                new_content = insert_import(content, import_stmt)
            elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                from nova.edit.typescript_editor import insert_import
                new_content = insert_import(content, import_stmt)
            else:
                new_content = import_stmt.strip() + "\n" + content
                
            return self.update_file(rel_path, new_content)
        except Exception as e:
            return EditResult.fail(f"Failed to insert import: {e}")

    def remove_function(self, rel_path: str, func_name: str) -> EditResult:
        """Remove a function from the file."""
        try:
            content = self.read_file(rel_path)
            ext = Path(rel_path).suffix.lower()
            
            if ext in (".py", ".pyi"):
                from nova.edit.python_editor import remove_function
                new_content = remove_function(content, func_name)
            elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                from nova.edit.typescript_editor import remove_function
                new_content = remove_function(content, func_name)
            else:
                return EditResult.fail("Remove function is not supported for generic files.")
                
            return self.update_file(rel_path, new_content)
        except Exception as e:
            return EditResult.fail(f"Failed to remove function: {e}")

    # ── Rollback ──────────────────────────────────────────────────

    def rollback_last_change(self) -> EditResult:
        """Revert the most recent reversible edit operation."""
        t0 = time.perf_counter()
        op = self.history.pop_last()
        if not op:
            return EditResult.fail("No reversible operations in history.")
            
        root = self._get_project_root()
        full_path = root / op.rel_path
        
        try:
            if op.kind == EditKind.CREATE:
                # Reverting create means deleting the file
                if full_path.exists():
                    full_path.unlink()
                self._notify_engines("deleted", op.rel_path)
                msg = f"Rollback: Deleted created file {op.rel_path}"
                diff_text = generate_diff(op.new_content or "", "", filename=op.rel_path).diff_text
            elif op.kind == EditKind.DELETE:
                # Reverting delete means restoring the file
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(op.old_content or "", encoding="utf-8")
                self._notify_engines("added", op.rel_path)
                msg = f"Rollback: Restored deleted file {op.rel_path}"
                diff_text = generate_diff("", op.old_content or "", filename=op.rel_path).diff_text
            elif op.kind in (EditKind.RENAME_FILE, EditKind.MOVE_FILE):
                # Reverting rename means moving it back
                dest_full = root / op.dest_rel_path if op.dest_rel_path else None
                if dest_full and dest_full.exists():
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_full.rename(full_path)
                    # Notify delete for new name, add for old name
                    self._notify_engines("deleted", op.dest_rel_path)
                    self._notify_engines("added", op.rel_path)
                    msg = f"Rollback: Moved {op.dest_rel_path} back to {op.rel_path}"
                    diff_text = ""
                else:
                    return EditResult.fail(f"Cannot rollback rename: renamed file not found at {op.dest_rel_path}")
            else:
                # Update, rename_symbol, insert_code, etc. mean writing old_content back
                if not full_path.exists():
                    return EditResult.fail(f"Cannot rollback: file does not exist at {op.rel_path}")
                current = full_path.read_text(encoding="utf-8", errors="replace")
                full_path.write_text(op.old_content or "", encoding="utf-8")
                self._notify_engines("modified", op.rel_path)
                msg = f"Rollback: Restored content of {op.rel_path}"
                diff_text = generate_diff(current, op.old_content or "", filename=op.rel_path).diff_text

            elapsed = time.perf_counter() - t0
            return EditResult.ok(
                message=msg,
                diff=diff_text,
                duration_s=round(elapsed, 3),
            )
        except Exception as e:
            return EditResult.fail(f"Rollback failed: {e}")

    def generate_diff(self, old_content: str, new_content: str, filename: str) -> str:
        """Public utility to generate unified diff text."""
        return generate_diff(old_content, new_content, filename).diff_text
