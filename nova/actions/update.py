from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import print_info, print_warning

class UpdateSystemAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "update_system"

    def execute(self, params: Dict[str, Any]) -> str:
        print_info("System Update Options:")
        print("  [1] Upgrade user profile packages ('nix profile upgrade --all')")
        print("  [2] Upgrade entire NixOS system ('sudo nixos-rebuild switch --upgrade')")
        print("  [c] Cancel")
        
        while True:
            choice = input("Enter choice (1, 2 or c): ").strip().lower()
            if choice == "c":
                return "System update cancelled."
            if choice == "1":
                cmd = ["nix", "profile", "upgrade", "--all"]
                confirm_message = "Upgrade all packages in active Nix profile"
                break
            elif choice == "2":
                cmd = ["sudo", "nixos-rebuild", "switch", "--upgrade"]
                confirm_message = "Rebuild entire NixOS configuration and download upgrades (requires sudo)"
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
