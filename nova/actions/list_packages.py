from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.packages import NixPackageManager
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_RESET, print_info

class ListPackagesAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "list_packages"

    def execute(self, params: Dict[str, Any]) -> str:
        import os
        source = "winget packages" if os.name == "nt" else "Nix user profile"
        print_info(f"Retrieving list of installed packages from {source}...")
        installed = NixPackageManager.get_installed_packages()
        if not installed:
            return f"No packages found installed via {source}."
        
        # Display list beautifully
        header = f"\n{COLOR_CYAN}{COLOR_BOLD}=== INSTALLED PACKAGES ({len(installed)}) ==={COLOR_RESET}"
        separator = "-" * 40
        lines = [header, separator]
        for name in sorted(installed):
            lines.append(f"  • {name}")
        lines.append(separator + "\n")
        
        return "\n".join(lines)
