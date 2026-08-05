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
    "flashlight.on",
    "flashlight.off",
    "flashlight.toggle",
    "flashlight_on",
    "flashlight_off",
    "youtube.play",
    "app.launch",
    "app_launch",
    "app_list",
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
    "finance",
    "chatgpt_action",
    "phone_connect",
    "phone_flashlight",
    "phone_vibrate",
    "phone_volume",
    "phone_camera",
    "phone_gallery",
    "phone_media_upload",
    "app_launch",
    "app_list",
    "accessibility_dump_tree",
    "accessibility_click",
    "accessibility_type",
    "accessibility_scroll",
    "global_gesture",
    "screen_capture",
    "screen_record_start",
    "screen_record_stop",
    "screen_stream_start",
    "screen_stream_stop",
    "screen_tap",
    "screen_swipe",
    "screen_type",
    "screen_state_get",
    "audio_capture_start",
    "audio_capture_stop",
    "voice_session_start",
    "voice_session_stop",
    "audio_play",
    "audio_stop",
    "microphone_mute",
    "microphone_unmute",
    "speaker_volume_set",
    "speaker_volume_get",
    "device_info",
    "device_health",
    "device_storage",
    "device_memory",
    "device_cpu",
    "device_network",
    "device_battery",
    "file_list",
    "file_upload",
    "file_download",
    "file_delete",
    "file_rename",
    "file_move",
    "file_copy",
    "device_logs",
    "device_performance",
    "device_processes",
    "device_crash_report",
    "adb_discover",
    "adb_pair",
    "adb_connect",
    "adb_disconnect",
    "adb_status",
    "adb_shell",
    "adb_install_apk",
    "adb_uninstall_apk",
    "adb_push",
    "adb_pull",
    "adb_screenshot",
    "adb_logcat",
    "adb_reboot",
    "adb_devices",
    "device_backup",
    "device_restore",
    "device_restart_companion",
    "device_restart_service",
    "device_clear_cache",
    "device_clear_logs",
    "device_update_status",
}

def clean_json_text(text: str) -> str:
    """Removes common markdown wrapper strings from LLM text."""
    text = text.strip()
    # Match ```json ... ``` or ``` ... ``` patterns
    match = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Handle comma-separated multiple JSON objects
    if ("}," in text or "}\n" in text or "}\r\n" in text) and not text.startswith("["):
        first_b = text.find("{")
        last_b = text.rfind("}")
        if first_b != -1 and last_b != -1 and last_b > first_b:
            sub = text[first_b:last_b + 1].strip()
            return f"[{sub}]"

    # Fallback to extracting anything between first '['/'{' and last ']'/'}'
    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
        if last_bracket != -1 and last_bracket > first_bracket:
            return text[first_bracket:last_bracket + 1].strip()

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
