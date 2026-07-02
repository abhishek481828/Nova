import os
import time
import uuid
import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nova.ai.planner")


# Predefined decomposition rules for intelligent task breakdown.
# All steps use STRUCTURED ACTIONS that map to Nova's Action Engine handlers.
# The Planner NEVER generates platform-specific shell commands.
DECOMPOSITION_RULES: Dict[str, List[Dict[str, Any]]] = {
    "build a flask website": [
        {
            "description": "Project Setup",
            "action_type": "project_setup",
            "required_skill": "files",
            "dependencies": []
        },
        {
            "description": "App Development",
            "action_type": "app_development",
            "required_skill": "files",
            "dependencies": ["Project Setup"]
        },
        {
            "description": "Execution",
            "action_type": "execution",
            "required_skill": "system",
            "dependencies": ["App Development"]
        }
    ],
    "project setup": [
        {
            "description": "Create project directory",
            "action_type": "file_action",
            "required_skill": "files",
            "dependencies": [],
            "metadata": {
                "action": "file_action",
                "params": {"operation": "create_directory", "path": "flask_project"}
            }
        },
        {
            "description": "Create Python virtual environment",
            "action_type": "command_execution",
            "required_skill": "system",
            "dependencies": ["Create project directory"],
            "metadata": {
                "action": "command_execution",
                "params": {"command": ["python", "-m", "venv", "flask_project/.venv"]}
            }
        },
        {
            "description": "Install Flask package",
            "action_type": "install_package",
            "required_skill": "system",
            "dependencies": ["Create Python virtual environment"],
            "metadata": {
                "action": "install_package",
                "params": {"package": "flask"}
            }
        }
    ],
    "app development": [
        {
            "description": "Generate Flask application file",
            "action_type": "file_action",
            "required_skill": "files",
            "dependencies": [],
            "metadata": {
                "action": "file_action",
                "params": {
                    "operation": "create",
                    "path": "flask_project/app.py",
                    "content": "from flask import Flask\napp = Flask(__name__)\n\n@app.route(\"/\")\ndef index():\n    return \"Hello from Nova!\"\n\nif __name__ == \"__main__\":\n    app.run(debug=True)\n"
                }
            }
        }
    ],
    "execution": [
        {
            "description": "Run Flask development server",
            "action_type": "run_project",
            "required_skill": "system",
            "dependencies": [],
            "metadata": {
                "action": "run_project",
                "params": {"project": "flask_project"}
            }
        }
    ],
    "open chrome": [
        {
            "description": "Open Browser",
            "action_type": "chromium_action",
            "required_skill": "browser",
            "dependencies": [],
            "metadata": {
                "action": "chromium_action",
                "params": {"operation": "open", "url": "google.com"}
            }
        },
        {
            "description": "Navigate to YouTube and search",
            "action_type": "chromium_action",
            "required_skill": "browser",
            "dependencies": ["Open Browser"],
            "metadata": {
                "action": "chromium_action",
                "params": {"operation": "search_youtube", "query": "lofi hip hop"}
            }
        }
    ],
    "git pull": [
        {
            "description": "Execute git pull in project",
            "action_type": "git_action",
            "required_skill": "github",
            "dependencies": [],
            "metadata": {
                "action": "git_action",
                "params": {"operation": "pull"}
            }
        },
        {
            "description": "Run automated test suite",
            "action_type": "run_project",
            "required_skill": "system",
            "dependencies": ["Execute git pull in project"],
            "metadata": {
                "action": "command_execution",
                "params": {"command": ["pytest"]}
            }
        }
    ]
}

# Subsystem configuration parameters for allowed skills and system resource definitions
ALLOWED_SKILLS: Set[str] = {
    "browser", "voice", "github", "weather", "files", "adb", "ocr", "email", "system", "music", "generic",
    "shell", "file_manager", "git", "chromium_action", "git_action", "command_execution", "generic_action"
}
ALLOWED_RESOURCES: Set[str] = {"network", "browser_session", "terminal", "audio_device"}

def determine_required_skills(description: str, action_type: str) -> List[str]:
    """
    Analyzes description and action_type to determine required skills.
    """
    skills = []
    desc_lower = description.lower()
    act_lower = action_type.lower()
    
    mappings = {
        "browser": ["browser", "chrome", "chromium", "navigate", "website", "youtube", "url", "tab", "web"],
        "voice": ["voice", "speech", "transcribe", "speak", "tts", "audio", "mic", "whisper", "sound"],
        "github": ["git", "github", "repository", "commit", "push", "pull", "repo", "clone"],
        "weather": ["weather", "forecast", "temperature", "rain", "sunny", "wind"],
        "files": ["file", "folder", "directory", "mkdir", "path", "generate files", "create folder", "templates"],
        "adb": ["adb", "android", "phone", "apk", "device"],
        "ocr": ["ocr", "extract text", "screen ocr", "read screen"],
        "email": ["email", "mail", "gmail", "send email", "inbox"],
        "system": ["system", "shell", "command", "script", "running", "specs", "volume", "brightness", "control", "screenshot"],
        "music": ["music", "song", "audio player", "spotify", "soundtrack"]
    }
    
    for skill, keywords in mappings.items():
        if skill in act_lower:
            skills.append(skill)
            continue
        for kw in keywords:
            if kw in desc_lower or kw in act_lower:
                skills.append(skill)
                break
                
    return skills if skills else ["generic"]


