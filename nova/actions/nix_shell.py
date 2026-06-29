from typing import Any, Dict, List
from nova.actions.base import BaseAction
from nova.executor import CommandExecutor

class NixShellAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "nix_shell"

    def execute(self, params: Dict[str, Any]) -> str:
        packages: List[str] = params.get("packages", [])
        if isinstance(packages, str):
            packages = [pkg.strip() for pkg in packages.split(",") if pkg.strip()]

        if not packages:
            return "Error: No packages specified to load into nix-shell."

        cmd = ["nix-shell", "-p"] + packages
        cmd_str = " ".join(cmd)

        # Check if we are running in daemon mode (over a socket connection)
        from nova.utils import _socket_conn
        if _socket_conn is not None:
            # Daemon mode cannot host interactive subprocess shells
            return (
                f"Interactive nix-shell launcher is only supported when running Nova directly in your terminal.\n"
                f"Please run the command manually in your shell:\n"
                f"  {cmd_str}"
            )

        # Local interactive CLI mode: run it
        print(f"\nLaunching temporary nix-shell with packages: {', '.join(packages)}...")
        print("Type 'exit' or press Ctrl+D to return to Nova.\n")
        
        exit_code = CommandExecutor.run_interactive(cmd)
        
        if exit_code == 0:
            return "Returned from nix-shell successfully."
        else:
            return f"nix-shell exited with code: {exit_code}"
