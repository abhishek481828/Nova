"""Built-In Intent Parser Python Binding."""

import re
from nova.mobile.command.registry import BuiltInIntent


class IntentParser:
    def parse(self, text: str) -> BuiltInIntent:
        clean = text.strip().lower()

        if any(w in clean for w in ("turn on flashlight", "flashlight on", "torch on")):
            return BuiltInIntent.FLASHLIGHT_ON
        if any(w in clean for w in ("turn off flashlight", "flashlight off", "torch off")):
            return BuiltInIntent.FLASHLIGHT_OFF

        if clean.startswith("call ") or clean.startswith("phone ") or clean.startswith("dial "):
            return BuiltInIntent.CALL_CONTACT
        if clean.startswith("send sms") or clean.startswith("send message") or clean.startswith("text "):
            return BuiltInIntent.SEND_SMS

        if clean.startswith("play ") and ("youtube" in clean or "video" in clean):
            return BuiltInIntent.PLAY_YOUTUBE
        if clean.startswith("play ") and "spotify" in clean:
            return BuiltInIntent.PLAY_SPOTIFY
        if clean.startswith("play ") or clean == "play music":
            return BuiltInIntent.PLAY_YOUTUBE

        if clean.startswith("open youtube"):
            return BuiltInIntent.PLAY_YOUTUBE
        if clean.startswith("open camera") or clean.startswith("launch camera"):
            return BuiltInIntent.OPEN_CAMERA
        if any(w in clean for w in ("take a photo", "take photo", "snap picture")):
            return BuiltInIntent.TAKE_PHOTO
        if clean.startswith("open chrome") or clean.startswith("open browser"):
            return BuiltInIntent.OPEN_BROWSER
        if clean.startswith("open maps") or clean.startswith("navigate to"):
            return BuiltInIntent.OPEN_MAPS
        if clean.startswith("open settings"):
            return BuiltInIntent.OPEN_SETTINGS
        if clean.startswith("open gallery") or clean.startswith("open photos"):
            return BuiltInIntent.OPEN_GALLERY
        if clean.startswith("open ") or clean.startswith("launch "):
            return BuiltInIntent.OPEN_APP

        if "volume" in clean:
            return BuiltInIntent.SET_VOLUME
        if "brightness" in clean:
            return BuiltInIntent.SET_BRIGHTNESS

        if "alarm" in clean:
            return BuiltInIntent.SET_ALARM
        if "timer" in clean:
            return BuiltInIntent.SET_TIMER
        if clean.startswith("search ") or clean.startswith("google "):
            return BuiltInIntent.SEARCH_GOOGLE

        if "notification" in clean:
            return BuiltInIntent.SHOW_NOTIFICATIONS
        if "battery" in clean:
            return BuiltInIntent.BATTERY_STATUS
        if "device status" in clean or "phone status" in clean:
            return BuiltInIntent.DEVICE_STATUS

        return BuiltInIntent.UNKNOWN
