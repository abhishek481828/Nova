import os
import shutil
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.utils import ask_confirmation, print_info, print_warning

class FileAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "file_action"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "").strip().lower()
        path = params.get("path", "").strip()
        content = params.get("content", "")

        if not path:
            return "Error: No file/directory path provided."

        path = os.path.abspath(os.path.expanduser(path))

        if operation == "create":
            try:
                # Ensure parent directory exists
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully created file: {path}"
            except Exception as e:
                return f"Failed to create file: {path}. Error: {e}"

        elif operation == "delete":
            if not os.path.exists(path):
                return f"Error: Path '{path}' does not exist."
            
            print_warning(f"Security Warning: You are about to delete '{path}'.")
            if not ask_confirmation("Proceed?"):
                return "Deletion cancelled by user."

            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                return f"Successfully deleted: {path}"
            except Exception as e:
                return f"Failed to delete '{path}'. Error: {e}"

        elif operation == "list":
            if not os.path.exists(path):
                return f"Error: Directory '{path}' does not exist."
            if not os.path.isdir(path):
                # Fallback to read if it is a file
                return self.execute({"action": "file_action", "operation": "read", "path": path})

            try:
                items = os.listdir(path)
                if not items:
                    return f"Directory '{path}' is empty."
                
                output = [f"Contents of {path}:"]
                for item in sorted(items):
                    full_item = os.path.join(path, item)
                    suffix = "/" if os.path.isdir(full_item) else ""
                    output.append(f"  {item}{suffix}")
                return "\n".join(output)
            except Exception as e:
                return f"Failed to list directory contents. Error: {e}"

        elif operation == "read":
            if not os.path.exists(path):
                return f"Error: File '{path}' does not exist."
            if os.path.isdir(path):
                return f"Error: Path '{path}' is a directory, cannot read contents as a file."

            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    # Limit output to 2000 chars to avoid flooding the terminal
                    text = f.read(2000)
                    if len(text) >= 2000:
                        text += "\n... [TRUNCATED]"
                return f"Contents of {path}:\n{text}"
            except Exception as e:
                return f"Failed to read file. Error: {e}"

        else:
            return f"Error: Unsupported file operation '{operation}'. Supported: create, delete, list, read."
