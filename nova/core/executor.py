import subprocess
from typing import List, Tuple, Union
from nova.logger import log_command, log_error
from nova.utils import ask_confirmation, print_warning

class CommandExecutor:
    _last_commands: List[str] = []

    @classmethod
    def clear_last_commands(cls) -> None:
        cls._last_commands.clear()

    @classmethod
    def get_last_commands(cls) -> List[str]:
        return list(cls._last_commands)

    @staticmethod
    def run_shell(
        cmd: Union[str, List[str]],
        require_confirmation: bool = False,
        confirm_message: str = "Execute system changes?",
        shell: bool = False,
        cwd: str = None
    ) -> Tuple[int, str, str]:
        """
        Runs a command synchronously and returns (exit_code, stdout, stderr).
        If require_confirmation is True, prompts the user before executing.
        """
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        
        if require_confirmation:
            print_warning(f"Security Warning: An action is trying to execute code that modifies the system:")
            print_warning(f"  Command: {cmd_str}")
            print_warning(f"  Action Details: {confirm_message}")
            if not ask_confirmation("Proceed?"):
                return -1, "", "Command execution aborted by user."
                
        # Record command
        CommandExecutor._last_commands.append(cmd_str)
        
        # Publish executing to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("command_executing", module="executor", status="running", metadata={"command": cmd_str, "type": "shell"})
        except Exception:
            pass
            
        try:
            result = subprocess.run(
                cmd,
                shell=shell,
                capture_output=True,
                text=True,
                check=False,
                cwd=cwd
            )
            log_command(cmd_str, result.returncode, result.stdout)
            
            # Publish executed to Dashboard
            try:
                from nova.dashboard.event_bus import emit
                emit("command_executed", module="executor", status="success" if result.returncode == 0 else "failed", metadata={
                    "command": cmd_str,
                    "returncode": result.returncode,
                    "output": result.stdout,
                    "error": result.stderr
                })
            except Exception:
                pass
                
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            log_error(f"Execution failed for command {cmd_str!r}", e)
            
            # Publish executed to Dashboard with exception
            try:
                from nova.dashboard.event_bus import emit
                emit("command_executed", module="executor", status="failed", metadata={
                    "command": cmd_str,
                    "returncode": -2,
                    "output": "",
                    "error": str(e)
                })
            except Exception:
                pass
                
            return -2, "", str(e)

    @staticmethod
    def run_background(cmd: Union[str, List[str]], shell: bool = False, cwd: str = None) -> Tuple[int, str]:
        """
        Spawns a background process without blocking CLI.
        """
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        CommandExecutor._last_commands.append(f"{cmd_str} (bg)")
        
        # Publish executing to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("command_executing", module="executor", status="running", metadata={"command": cmd_str, "type": "background"})
        except Exception:
            pass
            
        try:
            # Spawning as a new session so the background process detaches
            # and survives even if Nova exits.
            subprocess.Popen(
                cmd,
                shell=shell,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                cwd=cwd
            )
            log_command(f"{cmd_str} (launched in background)")
            
            # Publish executed to Dashboard
            try:
                from nova.dashboard.event_bus import emit
                emit("command_executed", module="executor", status="success", metadata={
                    "command": cmd_str,
                    "returncode": 0,
                    "output": "App launched successfully (PID spawned in background)",
                    "error": ""
                })
            except Exception:
                pass
                
            return 0, f"App launched successfully (PID spawned in background)"
        except Exception as e:
            log_error(f"Failed to start background command {cmd_str!r}", e)
            
            # Publish executed to Dashboard with exception
            try:
                from nova.dashboard.event_bus import emit
                emit("command_executed", module="executor", status="failed", metadata={
                    "command": cmd_str,
                    "returncode": -2,
                    "output": "",
                    "error": str(e)
                })
            except Exception:
                pass
                
            return -2, str(e)

    @staticmethod
    def run_interactive(cmd: Union[str, List[str]], shell: bool = False, cwd: str = None) -> int:
        """
        Runs a command interactively, sharing the terminal's stdin, stdout, and stderr.
        """
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        CommandExecutor._last_commands.append(cmd_str)
        
        # Publish executing to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("command_executing", module="executor", status="running", metadata={"command": cmd_str, "type": "interactive"})
        except Exception:
            pass
            
        try:
            result = subprocess.run(
                cmd,
                shell=shell,
                cwd=cwd
            )
            
            # Publish executed to Dashboard
            try:
                from nova.dashboard.event_bus import emit
                emit("command_executed", module="executor", status="success" if result.returncode == 0 else "failed", metadata={
                    "command": cmd_str,
                    "returncode": result.returncode,
                    "output": "Interactive run complete",
                    "error": ""
                })
            except Exception:
                pass
                
            return result.returncode
        except Exception as e:
            log_error(f"Interactive execution failed for command {cmd_str!r}", e)
            
            # Publish executed to Dashboard with exception
            try:
                from nova.dashboard.event_bus import emit
                emit("command_executed", module="executor", status="failed", metadata={
                    "command": cmd_str,
                    "returncode": -2,
                    "output": "",
                    "error": str(e)
                })
            except Exception:
                pass
                
            return -2
