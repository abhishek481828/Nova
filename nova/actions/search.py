from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.packages import NixPackageManager
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_RESET, print_info

class SearchPackageAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "search_package"

    def execute(self, params: Dict[str, Any]) -> str:
        query = params.get("query", "").strip()
        if not query:
            return "Error: No query provided to search."

        print_info(f"Searching nixpkgs for '{query}'...")
        results = NixPackageManager.search_packages(query)

        if not results:
            return f"No Nix packages found matching '{query}'."

        # Limit to top 15 results for clean CLI display
        display_limit = 15
        truncated_results = results[:display_limit]

        # Draw a beautiful, modern terminal table
        header = f"\n{COLOR_CYAN}{COLOR_BOLD}{'Flake Attribute (Package ID)':<40} | {'Version':<12} | {'Description':<50}{COLOR_RESET}"
        separator = "-" * 110
        lines = [header, separator]

        for pkg in truncated_results:
            name = pkg["name"]
            version = pkg["version"]
            desc = pkg["description"]
            # Truncate strings to prevent wrapping in basic console widths
            if len(name) > 38:
                name = name[:35] + "..."
            if len(version) > 10:
                version = version[:9] + "..."
            if len(desc) > 48:
                desc = desc[:45] + "..."
                
            lines.append(f"{name:<40} | {version:<12} | {desc:<50}")

        if len(results) > display_limit:
            lines.append(separator)
            lines.append(f"... and {len(results) - display_limit} more packages. Try a more specific query.")

        print("\n".join(lines) + "\n")
        return f"Found {len(results)} package(s) matching '{query}'."
