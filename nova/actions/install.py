import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.packages import PackageManager
from nova.core.executor import CommandExecutor
from nova.utils import ask_confirmation, print_info, print_warning, COLOR_BOLD, COLOR_CYAN, COLOR_RESET

class InstallPackageAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "install_package"

    def execute(self, params: Dict[str, Any]) -> str:
        package = params.get("package", "").strip()
        if not package:
            return "Error: No package name provided to install."

        if os.name == "nt":
            confirm_message = f"Install Windows package '{package}' using winget"
            exit_code, stdout, stderr = CommandExecutor.run_shell(
                ["winget", "install", "--id", package, "--accept-source-agreements", "--accept-package-agreements"],
                require_confirmation=True,
                confirm_message=confirm_message
            )
            if exit_code == 0:
                return f"Successfully installed package: {package}"
            elif exit_code == -1:
                return "Installation aborted by user."
            else:
                return f"Failed to install package: {package}. Error: {stderr or stdout}"

        # Linux fallback
        confirm_message = f"Install package '{package}'"
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            ["nix", "profile", "install", f"nixpkgs#{package}"],
            require_confirmation=True,
            confirm_message=confirm_message
        )
        if exit_code == 0:
            return f"Successfully installed package: {package}"
        elif exit_code == -1:
            return "Installation aborted by user."
        else:
            return f"Failed to install package: {package}. Error: {stderr or stdout}"
