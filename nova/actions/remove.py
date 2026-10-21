import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.packages import PackageManager
from nova.core.executor import CommandExecutor
from nova.utils import ask_confirmation, print_info, print_warning, COLOR_BOLD, COLOR_CYAN, COLOR_RESET

class RemovePackageAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "remove_package"

    def execute(self, params: Dict[str, Any]) -> str:
        package = params.get("package", "").strip()
        if not package:
            return "Error: No package name provided to remove."

        if os.name == "nt":
            confirm_message = f"Uninstall Windows package '{package}' using winget"
            exit_code, stdout, stderr = CommandExecutor.run_shell(
                ["winget", "uninstall", "--id", package, "--accept-source-agreements"],
                require_confirmation=True,
                confirm_message=confirm_message
            )
            if exit_code == 0:
                return f"Successfully uninstalled package: {package}"
            elif exit_code == -1:
                return "Uninstallation aborted by user."
            else:
                return f"Failed to uninstall package: {package}. Error: {stderr or stdout}"

        # Linux fallback
        confirm_message = f"Remove package '{package}'"
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            ["nix", "profile", "remove", package],
            require_confirmation=True,
            confirm_message=confirm_message
        )
        if exit_code == 0:
            return f"Successfully removed package: {package}"
        elif exit_code == -1:
            return "Removal aborted by user."
        else:
            return f"Failed to remove package: {package}. Error: {stderr or stdout}"
