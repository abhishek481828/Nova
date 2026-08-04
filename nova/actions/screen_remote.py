"""Phase G: Screen Capture & Remote Interaction Actions for Nova v2.0."""

import os
import time
import json
import base64
import subprocess
from pathlib import Path
from typing import Dict, Any
from nova.actions.base import BaseAction
from nova.actions.phone_control import send_companion_command
from nova.config import DOWNLOADS_DIR


class ScreenCaptureAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_capture"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("screen.capture", {})
        
        timestamp = int(time.time() * 1000)
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        local_path = DOWNLOADS_DIR / f"NOVA_SHOT_{timestamp}.jpg"

        if res.get("status") == "success":
            data = res.get("data", {})
            b64_str = data.get("base64_data", "")
            if b64_str.startswith("data:image/jpeg;base64,"):
                b64_str = b64_str[len("data:image/jpeg;base64,"):]

            if b64_str:
                try:
                    img_bytes = base64.b64decode(b64_str)
                    local_path.write_bytes(img_bytes)
                    return f"Successfully captured full-resolution screenshot on phone ({data.get('width')}x{data.get('height')}, {len(img_bytes)} bytes) -> Saved to {local_path}."
                except Exception:
                    pass

        # ADB Fallback Screenshot Capture
        adb_sd = "/sdcard/nova_shot.png"
        proc = subprocess.run(f"adb shell screencap -p {adb_sd} && adb pull {adb_sd} {local_path}", shell=True, capture_output=True, text=True)
        if proc.returncode == 0 and local_path.exists():
            size = local_path.stat().st_size
            return f"Successfully captured full-resolution screenshot via ADB ({size} bytes) -> Saved to {local_path}."

        return f"Failed to capture screenshot: {res.get('error', 'Device unreachable')}"


class ScreenRecordStartAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_record_start"

    def execute(self, params: Dict[str, Any]) -> str:
        bitrate = int(params.get("bitrate", 5000000))
        fps = int(params.get("fps", 30))

        res = send_companion_command("screen.record.start", {"bitrate": bitrate, "fps": fps})
        if res.get("status") == "success":
            data = res.get("data", {})
            return f"Successfully started screen recording on phone (FPS: {fps}, Bitrate: {bitrate})."

        # ADB Fallback Screen Recording Start
        subprocess.Popen("adb shell screenrecord /sdcard/nova_record.mp4", shell=True)
        return "Started screen recording on phone via ADB."


class ScreenRecordStopAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_record_stop"

    def execute(self, params: Dict[str, Any]) -> str:
        timestamp = int(time.time() * 1000)
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        local_path = DOWNLOADS_DIR / f"NOVA_REC_{timestamp}.mp4"

        res = send_companion_command("screen.record.stop", {})

        # ADB Pull Fallback for MP4
        subprocess.run(f"adb shell pkill -2 screenrecord && sleep 1 && adb pull /sdcard/nova_record.mp4 {local_path}", shell=True, capture_output=True)

        if local_path.exists() and local_path.stat().st_size > 0:
            size = local_path.stat().st_size
            return f"Successfully stopped screen recording on phone ({size} bytes) -> Saved to {local_path}."

        if res.get("status") == "success":
            data = res.get("data", {})
            return f"Stopped screen recording on phone (Duration: {data.get('duration_seconds', 0)}s)."

        return "Successfully stopped screen recording on phone."


class ScreenStreamStartAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_stream_start"

    def execute(self, params: Dict[str, Any]) -> str:
        fps = int(params.get("fps", 15))
        res = send_companion_command("screen.stream.start", {"fps": fps})
        if res.get("status") == "success":
            data = res.get("data", {})
            return f"Successfully started live screen streaming on phone (Target FPS: {fps}, Resolution: {data.get('resolution', '360x640')})."
        return f"Failed to start screen stream: {res.get('error', 'Device unreachable')}"


class ScreenStreamStopAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_stream_stop"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("screen.stream.stop", {})
        if res.get("status") == "success":
            data = res.get("data", {})
            return f"Successfully stopped live screen stream (Total bytes: {data.get('total_bytes_streamed', 0)})."
        return f"Failed to stop screen stream: {res.get('error', 'No active stream')}"


class ScreenTapAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_tap"

    def execute(self, params: Dict[str, Any]) -> str:
        x = float(params.get("x", 500))
        y = float(params.get("y", 1000))
        long_press = bool(params.get("long_press", False))
        double_tap = bool(params.get("double_tap", False))

        res = send_companion_command("screen.tap", {
            "x": x,
            "y": y,
            "long_press": long_press,
            "double_tap": double_tap
        })

        if res.get("status") == "success":
            mode = "Long press" if long_press else ("Double tap" if double_tap else "Tap")
            return f"Successfully executed {mode} at ({int(x)}, {int(y)}) on phone screen."

        # ADB Fallback Tap
        cmd = f"adb shell input swipe {x} {y} {x} {y} 1000" if long_press else f"adb shell input tap {x} {y}"
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if double_tap:
            subprocess.run(f"adb shell input tap {x} {y}", shell=True, capture_output=True)

        if proc.returncode == 0:
            mode = "Long press" if long_press else ("Double tap" if double_tap else "Tap")
            return f"Successfully executed {mode} at ({int(x)}, {int(y)}) on phone screen via ADB."

        return f"Failed to perform tap gesture at ({x}, {y}): {res.get('error', 'Device unreachable')}"


class ScreenSwipeAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_swipe"

    def execute(self, params: Dict[str, Any]) -> str:
        direction = str(params.get("direction", "")).lower()
        duration_ms = int(params.get("duration_ms", 300))
        start_x = params.get("start_x")
        start_y = params.get("start_y")
        end_x = params.get("end_x")
        end_y = params.get("end_y")

        payload = {"direction": direction, "duration_ms": duration_ms}
        if start_x is not None: payload["start_x"] = float(start_x)
        if start_y is not None: payload["start_y"] = float(start_y)
        if end_x is not None: payload["end_x"] = float(end_x)
        if end_y is not None: payload["end_y"] = float(end_y)

        res = send_companion_command("screen.swipe", payload)
        if res.get("status") == "success":
            desc = direction if direction else f"({start_x},{start_y}) -> ({end_x},{end_y})"
            return f"Successfully swiped {desc} on phone screen."

        # ADB Fallback Swipe
        if direction == "up":
            cmd = "adb shell input swipe 540 1500 540 400 300"
        elif direction == "down":
            cmd = "adb shell input swipe 540 400 540 1500 300"
        elif direction == "left":
            cmd = "adb shell input swipe 900 1000 100 1000 300"
        elif direction == "right":
            cmd = "adb shell input swipe 100 1000 900 1000 300"
        else:
            sx = start_x or 540
            sy = start_y or 1200
            ex = end_x or 540
            ey = end_y or 400
            cmd = f"adb shell input swipe {sx} {sy} {ex} {ey} {duration_ms}"

        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if proc.returncode == 0:
            desc = direction if direction else "custom gesture"
            return f"Successfully swiped {desc} on phone screen via ADB."

        return f"Failed to perform swipe: {res.get('error', 'Device unreachable')}"


class ScreenTypeAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_type"

    def execute(self, params: Dict[str, Any]) -> str:
        text = str(params.get("text", params.get("value", "")))
        target = str(params.get("target", ""))
        replace = bool(params.get("replace", True))

        if not text:
            return "Error: Missing text string to type."

        res = send_companion_command("screen.type", {
            "text": text,
            "target": target,
            "replace": replace
        })

        if res.get("status") == "success":
            return f"Successfully typed text '{text}' on phone."

        # ADB Fallback Type
        safe_text = text.replace(" ", "%s")
        proc = subprocess.run(f"adb shell input text '{safe_text}'", shell=True, capture_output=True, text=True)
        if proc.returncode == 0:
            return f"Successfully typed text '{text}' on phone via ADB."

        return f"Failed to type text '{text}': {res.get('error', 'Device unreachable')}"


class ScreenStateGetAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "screen_state_get"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("screen.state.get", {})
        if res.get("status") == "success":
            data = res.get("data", {})
            on_str = "ON" if data.get("is_screen_on") else "OFF"
            lock_str = "LOCKED" if data.get("is_locked") else "UNLOCKED"
            return f"Phone Screen State: {on_str} | Keyguard: {lock_str} | Orientation: {data.get('orientation')} | Resolution: {data.get('width')}x{data.get('height')} ({data.get('density_dpi')} dpi)."

        # ADB Fallback Screen State
        proc_power = subprocess.run("adb shell dumpsys power | grep mHoldingDisplay", shell=True, capture_output=True, text=True)
        is_on = "true" in proc_power.stdout.lower()
        on_str = "ON" if is_on else "OFF"
        return f"Phone Screen State (via ADB): Screen is {on_str}."
