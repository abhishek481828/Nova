import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.executor import CommandExecutor
from nova.utils import print_info, print_warning

class RunProjectAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "run_project"

    def execute(self, params: Dict[str, Any]) -> str:
        project_name = params.get("project", "").strip()
        
        # If no project name was parsed, but we have compile/run requests
        if not project_name:
            # Fallback to checking the current directory for compile targets
            if os.path.exists("main.cpp"):
                project_name = "main.cpp"
            elif os.path.exists("main.py"):
                project_name = "main.py"
            else:
                return "Error: No project name or source file specified."

        # Case 1: Compiling a single source file (like main.cpp) in current directory
        if project_name.endswith(".cpp"):
            if not os.path.exists(project_name):
                return f"Error: Source file '{project_name}' not found in current directory."
            
            output_bin = os.path.splitext(project_name)[0]
            print_info(f"Compiling {project_name} using g++...")
            
            # Synchronous compilation
            exit_code, stdout, stderr = CommandExecutor.run_shell(
                ["g++", "-O3", project_name, "-o", output_bin]
            )
            if exit_code != 0:
                return f"Compilation failed.\nStderr: {stderr}"
            
            print_info(f"Compilation succeeded. Running ./{output_bin}...")
            # Run binary in foreground
            exit_code, stdout, stderr = CommandExecutor.run_shell(f"./{output_bin}", shell=True)
            return f"Project finished execution (exit {exit_code}).\nStdout: {stdout}\nStderr: {stderr}"

        # Case 2: Running a python script directly
        if project_name.endswith(".py"):
            if not os.path.exists(project_name):
                return f"Error: Python script '{project_name}' not found."
            
            print_info(f"Running python3 {project_name}...")
            exit_code, stdout, stderr = CommandExecutor.run_shell(["python3", project_name])
            return f"Script finished execution (exit {exit_code}).\nStdout: {stdout}\nStderr: {stderr}"

        # Case 3: Finding a project folder in /home/nixos/Projects or current directory
        search_dirs = [os.getcwd(), "/home/nixos/Projects"]
        project_path = ""
        
        for base in search_dirs:
            candidate = os.path.join(base, project_name)
            if os.path.exists(candidate) and os.path.isdir(candidate):
                project_path = candidate
                break

        # Substring search in Projects folder if direct match fails
        if not project_path:
            projects_dir = "/home/nixos/Projects"
            if os.path.exists(projects_dir):
                folders = os.listdir(projects_dir)
                for folder in folders:
                    if project_name.lower() in folder.lower():
                        project_path = os.path.join(projects_dir, folder)
                        break
                
                # If substring match fails, attempt fuzzy matching on directory names
                if not project_path:
                    import difflib
                    matches = difflib.get_close_matches(project_name.lower(), [f.lower() for f in folders], n=1, cutoff=0.4)
                    if matches:
                        matched_lower = matches[0]
                        for folder in folders:
                            if folder.lower() == matched_lower:
                                project_path = os.path.join(projects_dir, folder)
                                print_warning(f"Project '{project_name}' not found. Auto-correcting to matched directory '{folder}'...")
                                break

        if not project_path:
            return f"Error: Could not locate project directory for '{project_name}'."

        print_info(f"Located project directory at: {project_path}")

        # Check for specific project types:
        # A: Node.js (including PhoneNotify server subfolder)
        node_paths = [project_path, os.path.join(project_path, "server")]
        for p in node_paths:
            if os.path.exists(os.path.join(p, "package.json")) or os.path.exists(os.path.join(p, "server.js")):
                print_info(f"Detected Node.js project in: {p}")
                # We will run this server in the background
                run_target = "server.js" if os.path.exists(os.path.join(p, "server.js")) else ""
                
                if run_target:
                    cmd = ["node", run_target]
                else:
                    cmd = ["npm", "start"]

                exit_code, msg = CommandExecutor.run_background(cmd, cwd=p)
                if exit_code == 0:
                    return f"Successfully started Node.js/PhoneNotify project server in the background."
                else:
                    return f"Failed to start project server: {msg}"

        # B: Rust project (Cargo)
        if os.path.exists(os.path.join(project_path, "Cargo.toml")):
            print_info("Detected Rust project. Running 'cargo run'...")
            exit_code, stdout, stderr = CommandExecutor.run_shell(["cargo", "run"], cwd=project_path)
            return f"Cargo run finished (exit {exit_code}).\nStdout: {stdout}\nStderr: {stderr}"

        # C: Python project with main.py
        if os.path.exists(os.path.join(project_path, "main.py")):
            print_info("Detected Python project. Running 'python3 main.py'...")
            exit_code, stdout, stderr = CommandExecutor.run_shell(["python3", "main.py"], cwd=project_path)
            return f"Python script finished (exit {exit_code}).\nStdout: {stdout}\nStderr: {stderr}"

        return f"Error: Project '{project_name}' detected at '{project_path}', but no runnable target (server.js, package.json, Cargo.toml, main.py, main.cpp) was identified."
