"""
nova.task.verification
~~~~~~~~~~~~~~~~~~~~~~
Post-edit step verification. Validates syntax, confirms file existences,
and runs tests via CommandExecutor to ensure zero regression.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

from nova.edit.validation import validate_file
from nova.core.executor import CommandExecutor

logger = logging.getLogger("nova.task.verification")


class StepVerifier:
    """
    Verifies the correctness of code changes applied during task steps.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def verify_files_exist(self, relative_paths: List[str]) -> Tuple[bool, List[str]]:
        """
        Verify that all expected files exist.
        """
        missing = []
        for rel in relative_paths:
            full = self.project_root / rel
            if not full.exists():
                missing.append(rel)
        if missing:
            return False, [f"Expected file(s) missing: {', '.join(missing)}"]
        return True, []

    def verify_syntax(self, relative_paths: List[str]) -> Tuple[bool, List[str]]:
        """
        Validate syntax for all modified/created files.
        """
        errors = []
        for rel in relative_paths:
            full = self.project_root / rel
            if not full.exists():
                continue
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
                val = validate_file(rel, content)
                if not val.is_valid:
                    errors.extend(val.errors)
            except Exception as e:
                errors.append(f"Failed to read/validate {rel}: {e}")
        if errors:
            return False, errors
        return True, []

    def run_tests(self, test_command: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Execute automated unit tests to verify changes did not break the project.
        """
        # If no explicit command is provided, try to discover one
        cmd = test_command
        if not cmd:
            if (self.project_root / "pytest.ini").exists() or (self.project_root / "conftest.py").exists() or (self.project_root / "nova").exists():
                cmd = "pytest"
            elif (self.project_root / "package.json").exists():
                cmd = "npm test"
            else:
                # No test setup discovered
                return True, []

        logger.info(f"[Verifier] Running tests: {cmd}")
        # Run test command synchronously
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            cmd,
            require_confirmation=False,
            cwd=str(self.project_root)
        )
        
        if exit_code != 0:
            err_msg = f"Test suite failed with exit code {exit_code}.\n"
            if stderr:
                err_msg += stderr[:500]
            elif stdout:
                err_msg += stdout[:500]
            return False, [err_msg]
            
        logger.info("[Verifier] Tests passed successfully.")
        return True, []

    def verify_step(
        self,
        files_created: List[str],
        files_modified: List[str],
        run_test_suite: bool = False,
        test_command: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        """
        Perform complete post-step verification: file checks, syntax checks, and unit tests.
        """
        # 1. Check file existence
        ok, errors = self.verify_files_exist(files_created)
        if not ok:
            return False, errors

        # 2. Syntax validation
        ok, errors = self.verify_syntax(files_created + files_modified)
        if not ok:
            return False, errors

        # 3. Test execution (optional)
        if run_test_suite:
            ok, errors = self.run_tests(test_command)
            if not ok:
                return False, errors

        return True, []
