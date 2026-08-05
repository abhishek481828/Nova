"""Phase F: Accessibility & App Automation System Actions for Nova v2.0."""

import json
from typing import Dict, Any
from nova.actions.base import BaseAction
from nova.actions.phone_control import send_companion_command, get_active_device_id


class AppLaunchAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "app_launch"

    def execute(self, params: Dict[str, Any]) -> str:
        app_name = str(params.get("app_name", params.get("target", "")))
        package_name = str(params.get("package_name", ""))
        search_query = str(params.get("search_query", params.get("query", "")))
        contact_name = str(params.get("contact_name", params.get("contact", "")))
        auto_play = bool(params.get("auto_play", True))

        app_lower = app_name.strip().lower()

        # 1. Direct WhatsApp Call Macro
        if contact_name and (app_lower in ("whatsapp", "wa") or "whatsapp" in package_name):
            import subprocess, time
            subprocess.run("adb shell am start -n com.whatsapp/.Main", shell=True, capture_output=True)
            time.sleep(1.8)
            subprocess.run("adb shell input tap 540 300", shell=True, capture_output=True)
            time.sleep(1.0)
            safe_contact = contact_name.replace(" ", "%s")
            subprocess.run(f"adb shell input text {safe_contact}", shell=True, capture_output=True)
            time.sleep(1.8)
            subprocess.run("adb shell input tap 540 500", shell=True, capture_output=True)
            time.sleep(1.8)
            subprocess.run("adb shell input tap 920 160", shell=True, capture_output=True)
            return f"Successfully initiated WhatsApp call to '{contact_name}' on phone."

        # 2. YouTube Launcher & Auto-Play (WebSocket + ADB Auto-Click)
        if app_lower in ("youtube", "yt") or "youtube" in package_name:
            res = send_companion_command("app.launch", {
                "app_name": "YouTube",
                "package_name": "com.google.android.youtube",
                "search_query": search_query,
                "auto_play": auto_play
            })
            if auto_play and search_query:
                import subprocess, time
                time.sleep(3.5)
                subprocess.run("adb shell input tap 540 800", shell=True, capture_output=True)
            return f"Successfully playing '{search_query or 'YouTube'}' on your phone!"

        # WebSocket Launch First for all apps (Chrome, WhatsApp, Photos, etc.)
        res = send_companion_command("app.launch", {
            "app_name": app_name,
            "package_name": package_name,
            "search_query": search_query,
            "contact_name": contact_name,
            "auto_play": auto_play
        })

        if res.get("status") == "success":
            data = res.get("data", {})
            return f"Successfully launched application '{data.get('app_name') or app_name}' on your phone!"

        # ADB Fallback if WebSocket is unreachable
        import subprocess
        if app_lower in ("chrome", "google chrome") or "chrome" in package_name:
            subprocess.run("adb shell am start -a android.intent.action.VIEW -d 'https://www.google.com' com.android.chrome", shell=True, capture_output=True)
            return "Successfully launched Chrome on phone via ADB."

        if app_lower in ("whatsapp", "wa") or "whatsapp" in package_name:
            subprocess.run("adb shell am start -n com.whatsapp/.Main", shell=True, capture_output=True)
            return "Successfully launched WhatsApp on phone via ADB."

        if app_lower in ("photos", "google photos") or "photos" in package_name:
            subprocess.run("adb shell monkey -p com.google.android.apps.photos -c android.intent.category.LAUNCHER 1", shell=True, capture_output=True)
            return "Successfully launched Photos on phone via ADB."

        return f"Failed to launch application '{app_name}': {res.get('error', 'App not found on phone')}"


class AppListAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "app_list"

    def execute(self, params: Dict[str, Any]) -> str:
        include_system = bool(params.get("include_system", False))
        res = send_companion_command("app.list", {"include_system": include_system})

        if res.get("status") == "success":
            apps = res.get("data", {}).get("apps", [])
            lines = [f"Found {len(apps)} installed applications on phone:"]
            for i, a in enumerate(apps[:30], 1):
                lines.append(f"  {i}. {a.get('app_name')} ({a.get('package_name')})")
            if len(apps) > 30:
                lines.append(f"  ... and {len(apps) - 30} more apps.")
            return "\n".join(lines)
        return f"Failed to list installed apps: {res.get('error', 'Device unreachable')}"


class AccessibilityDumpTreeAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "accessibility_dump_tree"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("accessibility.dump_tree", {})
        if res.get("status") == "success":
            data = res.get("data", {})
            pkg = data.get("package_name", "unknown")
            return f"Active Window UI Tree Dumped ({pkg}):\n" + json.dumps(data, indent=2)
        return f"Failed to dump UI tree: {res.get('error', 'Accessibility Service disabled')}"


class AccessibilityClickAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "accessibility_click"

    def execute(self, params: Dict[str, Any]) -> str:
        target = str(params.get("target", params.get("text", "")))
        res = send_companion_command("accessibility.click", {"target": target})
        if res.get("status") == "success":
            return f"Successfully clicked UI element matching '{target}'."
        return f"Failed to click UI element '{target}': {res.get('error', 'Element not found')}"


class AccessibilityTypeAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "accessibility_type"

    def execute(self, params: Dict[str, Any]) -> str:
        target = str(params.get("target", ""))
        text = str(params.get("text", params.get("value", "")))
        replace = bool(params.get("replace", True))

        res = send_companion_command("accessibility.type", {
            "target": target,
            "text": text,
            "replace": replace
        })
        if res.get("status") == "success":
            return f"Successfully typed text '{text}' into target input field."
        return f"Failed to type text '{text}': {res.get('error', 'Editable field not found')}"


class AccessibilityScrollAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "accessibility_scroll"

    def execute(self, params: Dict[str, Any]) -> str:
        direction = str(params.get("direction", "down")).lower()
        res = send_companion_command("accessibility.scroll", {"direction": direction})
        if res.get("status") == "success":
            return f"Successfully scrolled {direction} on phone screen."

        # ADB Fallback for Scrolling
        import subprocess
        swipe_cmd = "adb shell input swipe 540 1400 540 400 300" if direction in ("down", "forward") else "adb shell input swipe 540 400 540 1400 300"
        proc = subprocess.run(swipe_cmd, shell=True, capture_output=True, text=True)
        if proc.returncode == 0:
            return f"Successfully scrolled {direction} on phone screen."

        return f"Failed to scroll {direction}: {res.get('error', 'Active window not scrollable')}"


class GlobalGestureAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "global_gesture"

    def execute(self, params: Dict[str, Any]) -> str:
        gesture = str(params.get("gesture", params.get("action", "home"))).lower()
        action_map = {
            "home": "global.home",
            "back": "global.back",
            "recents": "global.recents",
            "recent": "global.recents",
            "notifications": "global.notifications",
            "quick_settings": "global.quick_settings"
        }
        cmd = action_map.get(gesture, "global.home")
        res = send_companion_command(cmd, {})
        if res.get("status") == "success":
            return f"Successfully performed global gesture '{gesture.upper()}'."

        # ADB Fallback for Gestures
        import subprocess
        key_map = {
            "home": "3",
            "back": "4",
            "recents": "187",
            "recent": "187",
            "notifications": "adb shell cmd statusbar expand-notifications",
            "quick_settings": "adb shell cmd statusbar expand-settings"
        }
        key = key_map.get(gesture, "3")
        adb_cmd = f"adb shell input keyevent {key}" if key.isdigit() else key
        proc = subprocess.run(adb_cmd, shell=True, capture_output=True, text=True)
        if proc.returncode == 0:
            return f"Successfully performed global gesture '{gesture.upper()}' on phone."

        return f"Failed to perform global gesture '{gesture}': {res.get('error', 'Global action failed')}"
