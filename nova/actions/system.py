from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor

class SystemAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "system_action"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "").strip().lower()
        if not operation:
            return "Error: No system operation provided."

        if operation == "storage":
            exit_code, stdout, stderr = CommandExecutor.run_shell(["df", "-h", "/"])
            if exit_code == 0:
                return f"Root storage capacity:\n{stdout.strip()}"
            else:
                return f"Failed to get storage capacity. Error: {stderr}"

        if operation == "reboot":
            cmd = ["systemctl", "reboot"]
            confirm_msg = "Reboot the system immediately"
        elif operation == "shutdown":
            cmd = ["systemctl", "poweroff"]
            confirm_msg = "Shut down the system immediately"
        elif operation == "suspend":
            cmd = ["systemctl", "suspend"]
            confirm_msg = "Suspend the system (put to sleep)"
        else:
            return f"Error: Unsupported system operation '{operation}'. Supported: reboot, shutdown, suspend."

        # Execute systemctl command with safety prompt
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            cmd,
            require_confirmation=True,
            confirm_message=confirm_msg
        )

        if exit_code == 0:
            return f"System operation '{operation}' initiated successfully."
        elif exit_code == -1:
            return f"System operation '{operation}' cancelled by user."
        else:
            return f"Failed to execute system operation '{operation}'. Error: {stderr}"
