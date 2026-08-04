"""Nova Action handlers for Samsung Galaxy A13 Phone Companion."""

import urllib.request
import json
from typing import Any, Dict
from nova.actions.base import BaseAction

SERVER_URL = "http://127.0.0.1:8000/api/v2/companion"


def get_active_device_id() -> str:
    """Dynamically resolves the currently online hardware device ID from the server dashboard."""
    try:
        resp = urllib.request.urlopen(f"{SERVER_URL}/dashboard", timeout=3).read()
        dash = json.loads(resp.decode())
        devices = dash.get("devices", [])
        for d in devices:
            did = d.get("device_id", "")
            if d.get("connection_status") == "ONLINE" and did.startswith("android-"):
                return did
        for d in devices:
            if d.get("connection_status") == "ONLINE":
                return d.get("device_id")
    except Exception:
        pass
    return "android-47bd6629"


def send_companion_command(action: str, payload: dict = None) -> dict:
    """Helper to send a WebSocket command to the active companion device."""
    try:
        device_id = get_active_device_id()
        data = {
            "device_id": device_id,
            "action": action,
            "payload": payload or {}
        }
        req_data = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            f"{SERVER_URL}/command",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=5).read()
        return json.loads(resp.decode())
    except Exception as e:
        return {"status": "error", "error": f"Companion server unreachable ({e})"}


class PhoneConnectAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "phone_connect"

    def execute(self, params: Dict[str, Any]) -> str:
        try:
            resp = urllib.request.urlopen(f"{SERVER_URL}/dashboard", timeout=3).read()
            dash = json.loads(resp.decode())
            count = dash.get("connected_count", 0)
            devices = dash.get("devices", [])
            if count > 0:
                online_names = [d.get("device_name", "Phone") for d in devices if d.get("connection_status") == "ONLINE"]
                return f"Successfully connected to companion device: {', '.join(online_names)} over WebSocket."
            return "Phone companion server is online, but no active WebSocket companion device is currently connected."
        except Exception as e:
            return f"Failed to connect to phone companion server: {e}"


class PhoneFlashlightAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "phone_flashlight"

    def execute(self, params: Dict[str, Any]) -> str:
        state = str(params.get("state", "toggle")).lower()
        if state not in ("on", "off", "toggle"):
            state = "toggle"

        try:
            res = send_companion_command(f"flashlight.{state}", {"state": state})
            if res.get("status") == "success":
                return f"Successfully turned {state.upper()} the phone flashlight!"
            return f"Failed to toggle flashlight: {res.get('error', 'Device unreachable')}"
        except Exception as e:
            return f"Error executing flashlight command: {e}"


class PhoneVibrateAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "phone_vibrate"

    def execute(self, params: Dict[str, Any]) -> str:
        try:
            res = send_companion_command("vibration.short", {"duration_ms": 300})
            if res.get("status") == "success":
                return "Successfully triggered phone vibration pulse!"
            return f"Failed to vibrate phone: {res.get('error', 'Device unreachable')}"
        except Exception as e:
            return f"Error executing vibration command: {e}"


class PhoneVolumeAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "phone_volume"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = str(params.get("operation", "set")).lower()
        level = params.get("level")

        try:
            # GET current volume
            if operation == "get":
                res = send_companion_command("volume.get")
                if res.get("status") == "success":
                    vol = res.get("data", {}).get("volume_level", "unknown")
                    return f"Phone volume is currently at {vol}%."
                return f"Failed to get volume: {res.get('error', 'Device unreachable')}"

            # MUTE
            if operation == "mute":
                res = send_companion_command("volume.mute")
                if res.get("status") == "success":
                    return "Phone volume muted!"
                return f"Failed to mute: {res.get('error', 'Device unreachable')}"

            # DECREASE by percentage
            if operation == "decrease":
                amount = int(level) if level is not None else 10
                cur_res = send_companion_command("volume.get")
                current = 100
                if cur_res.get("status") == "success":
                    current = int(cur_res.get("data", {}).get("volume_level", 100))
                new_level = max(0, current - amount)
                res = send_companion_command("volume.set", {"level": new_level})
                if res.get("status") == "success":
                    return f"Decreased phone volume from {current}% to {new_level}% (reduced by {amount}%)."
                return f"Failed to decrease volume: {res.get('error', 'Device unreachable')}"

            # INCREASE by percentage
            if operation == "increase":
                amount = int(level) if level is not None else 10
                cur_res = send_companion_command("volume.get")
                current = 50
                if cur_res.get("status") == "success":
                    current = int(cur_res.get("data", {}).get("volume_level", 50))
                new_level = min(100, current + amount)
                res = send_companion_command("volume.set", {"level": new_level})
                if res.get("status") == "success":
                    return f"Increased phone volume from {current}% to {new_level}% (raised by {amount}%)."
                return f"Failed to increase volume: {res.get('error', 'Device unreachable')}"

            # SET to absolute level (default)
            target = int(level) if level is not None else 80
            res = send_companion_command("volume.set", {"level": target})
            if res.get("status") == "success":
                return f"Successfully set phone volume to {target}%!"
            return f"Failed to set volume: {res.get('error', 'Device unreachable')}"

        except Exception as e:
            return f"Error executing volume command: {e}"


class PhoneCameraAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "phone_camera"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = str(params.get("operation", "capture_photo")).lower()
        facing = str(params.get("camera_selector", "back")).lower()

        try:
            if operation == "capture_photo":
                res = send_companion_command("camera.capture_photo", {"camera_selector": facing})
                if res.get("status") == "success":
                    data = res.get("data", {})
                    file_name = data.get("file_name", "captured_photo.jpg")
                    b64_str = data.get("file_base64")

                    import os, base64, subprocess
                    downloads_dir = os.path.expanduser("~/Projects/Nova/downloads")
                    os.makedirs(downloads_dir, exist_ok=True)

                    if b64_str:
                        raw_bytes = base64.b64decode(b64_str)
                        out_path = os.path.join(downloads_dir, file_name)
                        with open(out_path, "wb") as f:
                            f.write(raw_bytes)

                        try:
                            subprocess.Popen(["xdg-open", out_path])
                        except Exception:
                            pass

                        return f"Photo captured successfully!\n  • Saved in Phone Gallery: {data.get('phone_path')}\n  • Saved on Laptop: file://{out_path}\n  • Displayed on laptop screen via image viewer."
                    return f"Photo captured on phone gallery ({data.get('phone_path', 'Pictures/Nova')})!"
                return f"Failed to capture photo: {res.get('error', 'Device unreachable')}"

            elif operation == "record_video":
                dur = int(params.get("duration_seconds", 5))
                res = send_companion_command("camera.record_video", {"camera_selector": facing, "duration_seconds": dur})
                if res.get("status") == "success":
                    data = res.get("data", {})
                    return f"Video recorded successfully! File: {data.get('file_name')} ({dur} seconds)."
                return f"Failed to record video: {res.get('error', 'Device unreachable')}"

            elif operation == "scan_qr":
                res = send_companion_command("camera.scan_qr", {"camera_selector": facing})
                if res.get("status") == "success":
                    data = res.get("data", {})
                    return f"QR Code Scanned successfully! Result: {data.get('qr_data')} (Type: {data.get('type')})."
                return f"Failed to scan QR code: {res.get('error', 'Device unreachable')}"

            elif operation == "ocr_scan":
                res = send_companion_command("camera.ocr_scan", {"camera_selector": facing})
                if res.get("status") == "success":
                    data = res.get("data", {})
                    return f"OCR Text Extracted successfully: \"{data.get('extracted_text')}\" (Confidence: {data.get('confidence')})."
                return f"Failed to extract text via OCR: {res.get('error', 'Device unreachable')}"

            return f"Unsupported camera operation: {operation}"

        except Exception as e:
            return f"Error executing camera command: {e}"


class PhoneGalleryAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "phone_gallery"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = str(params.get("operation", "list")).lower()
        limit = int(params.get("limit", 5))
        media_id = params.get("media_id")
        index = params.get("index")

        import os, base64, subprocess

        downloads_dir = os.path.expanduser("~/Projects/Nova/downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        try:
            # View / Fetch specific photo
            if operation in ("fetch", "view", "open") or media_id or index:
                target_id = media_id
                file_name = f"photo_{target_id or index or 'recent'}.jpg"

                if not target_id and (index or operation in ("fetch", "view", "open")):
                    # Get recent media list to resolve index
                    rec_res = send_companion_command("gallery.get_recent", {"limit": 10})
                    if rec_res.get("status") == "success":
                        media_items = rec_res.get("data", {}).get("media", [])
                        idx = int(index) - 1 if index else 0
                        if 0 <= idx < len(media_items):
                            target_id = media_items[idx].get("media_id")
                            file_name = media_items[idx].get("file_name", file_name)

                if not target_id:
                    return "Could not resolve valid media_id to view."

                res = send_companion_command("gallery.fetch", {"media_id": target_id})
                if res.get("status") == "success":
                    b64_str = res.get("data", {}).get("file_base64", "")
                    if b64_str:
                        raw_bytes = base64.b64decode(b64_str)
                        out_path = os.path.join(downloads_dir, file_name)
                        with open(out_path, "wb") as f:
                            f.write(raw_bytes)

                        # Open image viewer on Linux
                        try:
                            subprocess.Popen(["xdg-open", out_path])
                        except Exception:
                            pass

                        return f"Downloaded '{file_name}' ({len(raw_bytes)} bytes) to {out_path} and opened in your image viewer!"
                    return "Image bytes were empty or unavailable."
                return f"Failed to fetch photo from phone: {res.get('error', 'Device unreachable')}"

            # Default: list recent photos
            res = send_companion_command("gallery.get_recent", {"limit": limit})
            if res.get("status") == "success":
                media = res.get("data", {}).get("media", [])
                if not media:
                    return "No recent media items found in phone gallery."
                lines = [f"Found {len(media)} recent media item(s) in phone gallery:"]
                for i, m in enumerate(media, 1):
                    lines.append(f"  {i}. {m.get('file_name')} (ID: {m.get('media_id')}) - {m.get('size_bytes')} bytes")
                lines.append("\nTip: Type 'view photo 1' or 'open photo 1' to view it on your PC screen!")
                return "\n".join(lines)
            return f"Failed to list gallery: {res.get('error', 'Device unreachable')}"
        except Exception as e:
            return f"Error executing gallery command: {e}"


class PhoneMediaUploadAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "phone_media_upload"

    def execute(self, params: Dict[str, Any]) -> str:
        import os, base64, json, urllib.request, subprocess
        target_path = params.get("file_path") or params.get("local_path") or params.get("file_name")
        downloads_dir = os.path.expanduser("~/Projects/Nova/downloads")

        # If no valid path provided, search for latest captured photo in downloads folder
        if not target_path or not os.path.exists(target_path):
            if os.path.exists(downloads_dir):
                files = [os.path.join(downloads_dir, f) for f in os.listdir(downloads_dir) if f.endswith((".jpg", ".jpeg", ".png"))]
                if files:
                    target_path = max(files, key=os.path.getmtime)

        # If still no file found, attempt fetching latest from phone gallery
        if not target_path or not os.path.exists(target_path):
            try:
                rec_res = send_companion_command("gallery.get_recent", {"limit": 1})
                if rec_res.get("status") == "success":
                    items = rec_res.get("data", {}).get("media", [])
                    if items:
                        m_id = items[0].get("media_id")
                        f_name = items[0].get("file_name", "phone_photo.jpg")
                        f_res = send_companion_command("gallery.fetch", {"media_id": m_id})
                        if f_res.get("status") == "success":
                            b64 = f_res.get("data", {}).get("file_base64")
                            if b64:
                                os.makedirs(downloads_dir, exist_ok=True)
                                target_path = os.path.join(downloads_dir, f_name)
                                with open(target_path, "wb") as f:
                                    f.write(base64.b64decode(b64))
            except Exception:
                pass

        if not target_path or not os.path.exists(target_path):
            return "No valid image file found to upload."

        file_name = os.path.basename(target_path)
        file_type = "image/png" if file_name.endswith(".png") else "image/jpeg"

        try:
            with open(target_path, "rb") as f:
                raw_bytes = f.read()

            file_base64 = base64.b64encode(raw_bytes).decode("utf-8")
            device_id = get_active_device_id()

            payload = {
                "device_id": device_id,
                "file_name": file_name,
                "file_type": file_type,
                "file_base64": file_base64
            }

            # Try primary v2 endpoint first, then legacy endpoint
            upload_urls = [
                f"{SERVER_URL}/api/v2/companion/media/upload",
                f"{SERVER_URL}/media/upload"
            ]

            res = None
            for url in upload_urls:
                try:
                    req_data = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=req_data,
                        headers={"Content-Type": "application/json"}
                    )
                    resp = urllib.request.urlopen(req, timeout=10).read()
                    res = json.loads(resp.decode())
                    if res.get("status") == "uploaded":
                        break
                except Exception:
                    continue

            if res and res.get("status") == "uploaded":
                out_path = res.get("file_path")
                if out_path and os.path.exists(out_path):
                    try:
                        subprocess.Popen(["xdg-open", out_path])
                    except Exception:
                        pass
                return f"Successfully uploaded real image ({len(raw_bytes)} bytes) to Nova Core storage!\n  • File: {res.get('file_name')}\n  • Saved Path: file://{out_path}"

            return f"Failed to upload media: {res}"
        except Exception as e:
            return f"Error executing media upload: {e}"

