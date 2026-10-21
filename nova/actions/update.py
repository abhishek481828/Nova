from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import print_info, print_warning

class UpdateSystemAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "update_system"

    def execute(self, params: Dict[str, Any]) -> str:
        import os
        if os.name == "nt":
            print_info("Windows Update Options:")
            print("  [1] Upgrade all installed applications ('winget upgrade --all')")
            print("  [c] Cancel")
            choice = input("Enter choice (1 or c): ").strip().lower()
            if choice != "1":
                return "System update cancelled."
            cmd = ["winget", "upgrade", "--all", "--accept-source-agreements", "--accept-package-agreements"]
            confirm_message = "Upgrade all Windows packages using winget"
            exit_code, stdout, stderr = CommandExecutor.run_shell(
                cmd,
                require_confirmation=True,
                confirm_message=confirm_message
            )
            if exit_code == 0:
                return "Windows package upgrades completed successfully."
            elif exit_code == -1:
                return "System upgrade aborted by user."
            else:
                return f"Failed system upgrade. Error: {stderr or stdout}"

        print_info("System Update Options:")
        print("  [1] Upgrade user packages ('nix profile upgrade --all')")
        print("  [c] Cancel")
        
        while True:
            choice = input("Enter choice (1 or c): ").strip().lower()
            if choice == "c":
                return "System update cancelled."
            if choice == "1":
                cmd = ["nix", "profile", "upgrade", "--all"]
                confirm_message = "Upgrade all packages in active user profile"
                break
            print("Invalid choice, try again.")

        exit_code, stdout, stderr = CommandExecutor.run_shell(
            cmd,
            require_confirmation=True,
            confirm_message=confirm_message
        )

        if exit_code == 0:
            return "System upgrade completed successfully."
        elif exit_code == -1:
            return "System upgrade aborted by user."
        else:
            return f"Failed system upgrade. Error: {stderr}"
