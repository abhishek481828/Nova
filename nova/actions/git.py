import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import print_info

class GitAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "git_action"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "").strip().lower()
        repo_path = params.get("repo_path", "").strip()
        message = params.get("message", "").strip()

        if not repo_path:
            repo_path = os.getcwd()
        else:
            repo_path = os.path.expanduser(repo_path)

        if not os.path.exists(repo_path):
            return f"Error: Git repository path '{repo_path}' does not exist."

        if operation == "status":
            cmd = ["git", "status"]
            require_confirm = False
            confirm_msg = ""
        elif operation == "pull":
            cmd = ["git", "pull"]
            require_confirm = False
            confirm_msg = ""
        elif operation == "push":
            cmd = ["git", "push"]
            require_confirm = True
            confirm_msg = f"Push changes from repository '{repo_path}' to remote server"
        elif operation == "commit":
            if not message:
                message = input("Enter commit message: ").strip()
                if not message:
                    return "Error: Commit message is required."
            cmd = ["git", "commit", "-m", message]
            require_confirm = False
            confirm_msg = ""
        else:
            return f"Error: Unsupported Git operation '{operation}'. Supported: status, pull, push, commit."

        print_info(f"Running git {operation} in {repo_path}...")
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            cmd,
            require_confirmation=require_confirm,
            confirm_message=confirm_msg,
            cwd=repo_path
        )

        if exit_code == 0:
            output = stdout if stdout else "Success (no output)."
            return f"Git {operation} completed successfully.\n{output}"
        elif exit_code == -1:
            return f"Git {operation} was cancelled by the user."
        else:
            return f"Git {operation} failed (Exit {exit_code}).\nStderr: {stderr}\nStdout: {stdout}"
