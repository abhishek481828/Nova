from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor

class NixosConfigAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "nixos_config"

    def execute(self, params: Dict[str, Any]) -> str:
        option = params.get("option", "").strip()
        if not option:
            return "Error: No NixOS option name provided to inspect."

        # Execute nixos-option command to query properties of the specified option
        exit_code, stdout, stderr = CommandExecutor.run_shell(["nixos-option", option])
        
        if exit_code == 0:
            return stdout.strip()
        else:
            # If the option fails (e.g. invalid name), return stderr
            error_msg = stderr.strip() if stderr.strip() else f"Option '{option}' not found or not defined."
            return f"Failed to inspect NixOS option '{option}'. Error: {error_msg}"
