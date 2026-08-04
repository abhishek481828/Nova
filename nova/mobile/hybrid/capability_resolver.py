"""Capability Resolver — Phone vs. Nova Core capability registry."""

import logging
from nova.mobile.hybrid.strategy import ExecutionTarget

logger = logging.getLogger("nova.mobile.hybrid.capability_resolver")

PHONE_INTENTS = {
    "CALL_CONTACT", "SEND_SMS", "OPEN_APP", "PLAY_YOUTUBE", "PLAY_SPOTIFY",
    "SET_VOLUME", "SET_BRIGHTNESS", "FLASHLIGHT_ON", "FLASHLIGHT_OFF",
    "OPEN_CAMERA", "TAKE_PHOTO", "OPEN_SETTINGS", "OPEN_MAPS", "SET_ALARM",
    "SET_TIMER", "SHOW_NOTIFICATIONS", "READ_NOTIFICATIONS", "OPEN_BROWSER",
    "SEARCH_GOOGLE", "OPEN_GALLERY", "COPY_TEXT", "PASTE_TEXT",
    "DEVICE_STATUS", "BATTERY_STATUS"
}

NOVA_CORE_KEYWORDS = {
    "explain", "summarize", "summary", "analyze", "analyse",
    "write code", "debug", "generate", "translate", "research",
    "what is", "how does", "why does", "define", "tell me about",
    "search the web", "browse", "open file", "read pdf", "read document",
    "project", "automate", "script", "process", "quantum", "philosophy",
    "history of", "science", "math", "algorithm", "data structure",
    "compare", "difference between", "reasoning", "long answer"
}


class CapabilityResolver:
    def resolve_target(self, intent_name: str, raw_text: str) -> ExecutionTarget:
        clean = raw_text.strip().lower()

        if intent_name in PHONE_INTENTS and intent_name != "UNKNOWN":
            logger.info(f"[{intent_name}] → LOCAL_ANDROID via intent registry")
            return ExecutionTarget.LOCAL_ANDROID

        for keyword in NOVA_CORE_KEYWORDS:
            if keyword in clean:
                logger.info(f"[{intent_name}] → NOVA_CORE via keyword '{keyword}'")
                return ExecutionTarget.NOVA_CORE

        logger.info(f"[{intent_name}] → LOCAL_ANDROID (default)")
        return ExecutionTarget.LOCAL_ANDROID

    def is_phone_capability(self, intent_name: str) -> bool:
        return intent_name in PHONE_INTENTS

    def is_nova_core_required(self, raw_text: str) -> bool:
        clean = raw_text.strip().lower()
        return any(kw in clean for kw in NOVA_CORE_KEYWORDS)
