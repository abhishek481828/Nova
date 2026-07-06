import json
import re
from typing import Any, Dict, List, Optional
from nova.logger import log_error

VALID_ACTIONS = {
    "open_app",
    "install_package",
    "remove_package",
    "search_package",
    "update_system",
    "run_project",
    "git_action",
    "file_action",
    "browser_action",
    "system_action",
    "chat_response",
    "check_installed",
    "adb_action",
    "diagnose",
    "close_app",
    "system_resources",
    "nixos_config",
    "nix_shell",
    "update_user_profile",
    "system_status",
    "list_packages",
    "volume_control",
    "brightness_control",
    "charge_control",
    "desktop_control",
    "wifi_control",
    "rich_system_info",
    "chromium_action",
    "chrome_action",
    "tavily_search",
    "weather",
    "crypto_price",
    "news",
    "github_action",
    "telegram",
    "currency",
    "ocr",
    "ip_info",
    "tmdb",
    "finance"
}

def clean_json_text(text: str) -> str:
    """Removes common markdown wrapper strings from LLM text."""
    text = text.strip()
    # Match ```json ... ``` or ``` ... ``` patterns
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Fallback to extracting anything between first '{' and last '}'
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1].strip()
        
    return text

def parse_and_validate_action(raw_response: str) -> Optional[List[Dict[str, Any]]]:
    """
    Parses a raw string response into a list of actions, and ensures they conform to 
    expected action structures.
    """
    if not raw_response:
        return None
        
    cleaned_text = clean_json_text(raw_response)
    try:
        data = json.loads(cleaned_text)
        
        # Normalize into a list of actions
        actions = []
        if isinstance(data, list):
            actions = data
        elif isinstance(data, dict):
            if "actions" in data and isinstance(data["actions"], list):
                actions = data["actions"]
            else:
                actions = [data]
        else:
            log_error(f"Parsed JSON is not a list or dictionary: {data}")
            return None

        validated_actions = []
        for act in actions:
            if not isinstance(act, dict):
                continue
                
            action = act.get("action")
            if not action or action not in VALID_ACTIONS:
                # Fallback for general conversational, unrecognized, or null/none responses
                message_text = (
                    act.get("message")
                    or act.get("response")
                    or act.get("text")
                    or act.get("result")
                    or ""
                )
                message_str = str(message_text).strip()
                if not message_str or message_str.lower() in ("none", "null", "undefined"):
                    message_str = "Hello! I am Nova, your terminal assistant. I can open apps, search/install packages, manage git repos, run projects, or manage files."
                    
                act = {
                    "action": "chat_response",
                    "message": message_str
                }
            validated_actions.append(act)

        return validated_actions if validated_actions else None
        
    except json.JSONDecodeError as e:
        log_error(f"Failed to decode JSON from text: {cleaned_text!r}", e)
        return None
