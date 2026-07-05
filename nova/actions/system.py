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

        if operation == "shutdown":
            cmd = ["systemctl", "poweroff"]
            confirm_msg = "Shut down the system immediately"
        elif operation == "suspend":
            cmd = ["systemctl", "suspend", "-i"]
            confirm_msg = "Suspend the system (put to sleep)"
        else:
            return f"Error: Unsupported system operation '{operation}'. Supported: shutdown, suspend."

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

            err_msg = f"Failed to execute system operation '{operation}'. Error: {stderr.strip()}"
            if operation == "suspend" and ("access denied" in stderr.lower() or "permission" in stderr.lower() or "auth" in stderr.lower() or "password" in stderr.lower()):
                err_msg += (
                    "\n\n[Troubleshooting] This Access Denied error occurs because the background "
                    "systemd user service does not run inside an active login seat session. "
                    "To fix this, you can authorize users to suspend the system by adding the following Polkit rule "
                    "to your NixOS configuration (e.g. `/etc/nixos/configuration.nix`):\n\n"
                    "security.polkit.extraConfig = ''\n"
                    "  polkit.addRule(function(action, subject) {\n"
                    "    if ((action.id == \"org.freedesktop.login1.suspend\" ||\n"
                    "         action.id == \"org.freedesktop.login1.suspend-multiple-sessions\" ||\n"
                    "         action.id == \"org.freedesktop.login1.suspend-ignore-inhibit\") &&\n"
                    "        (subject.isInGroup(\"wheel\") || subject.user == \"nixos\")) {\n"
                    "      return polkit.Result.YES;\n"
                    "      }\n"
                    "  });\n"
                    "'';\n\n"
                    "After adding this, apply changes by running: `sudo nixos-rebuild switch`"
                )
            return err_msg
