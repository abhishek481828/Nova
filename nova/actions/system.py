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

        import os
        import psutil

        if operation == "storage":
            if os.name == "nt":
                du = psutil.disk_usage("C:\\")
                total_g = du.total / (1024 ** 3)
                used_g = du.used / (1024 ** 3)
                free_g = du.free / (1024 ** 3)
                return f"C: Storage Capacity:\nTotal: {total_g:.1f} GiB | Used: {used_g:.1f} GiB ({du.percent}%) | Free: {free_g:.1f} GiB"
            else:
                exit_code, stdout, stderr = CommandExecutor.run_shell(["df", "-h", "/"])
                if exit_code == 0:
                    return f"Root storage capacity:\n{stdout.strip()}"
                else:
                    return f"Failed to get storage capacity. Error: {stderr}"

        if operation == "shutdown":
            if os.name == "nt":
                cmd = ["shutdown", "/s", "/t", "0"]
            else:
                cmd = ["systemctl", "poweroff"]
            confirm_msg = "Shut down the system immediately"
        elif operation == "suspend":
            if os.name == "nt":
                cmd = ["powershell", "-NoProfile", "-Command", "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"]
            else:
                cmd = ["systemctl", "suspend", "-i"]
            confirm_msg = "Suspend the system (put to sleep)"
        else:
            return f"Error: Unsupported system operation '{operation}'. Supported: shutdown, suspend, storage."

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
            # Check if it failed due to permissions and attempt sudo -n fallback
            if "access denied" in stderr.lower() or "permission" in stderr.lower() or "auth" in stderr.lower() or "password" in stderr.lower():
                fallback_cmd = ["sudo", "-n"] + cmd
                exit_code_fb, stdout_fb, stderr_fb = CommandExecutor.run_shell(
                    fallback_cmd,
                    require_confirmation=False
                )
                if exit_code_fb == 0:
                    return f"System operation '{operation}' initiated successfully (via passwordless sudo)."
                else:
                    stderr = stderr_fb

            return f"Failed to execute system operation '{operation}'. Error: {stderr.strip()}"
