"""Command Dispatcher Python Binding."""

import time
import logging
from typing import Dict
from nova.mobile.command.registry import BuiltInIntent
from nova.mobile.command.result import CommandResult

logger = logging.getLogger("nova.mobile.command.dispatcher")


class CommandDispatcher:
    def dispatch(self, command_id: str, intent: BuiltInIntent, entities: Dict[str, str]) -> CommandResult:
        start_time = time.time()
        logger.info(f"Dispatching intent {intent.value} with entities: {entities}")

        if intent == BuiltInIntent.CALL_CONTACT:
            contact = entities.get("contact", "unknown")
            return CommandResult(
                command_id, intent, True,
                spoken_response=f"Calling {contact}.",
                plugin_used="CallHandler",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == BuiltInIntent.SEND_SMS:
            contact = entities.get("contact", "unknown")
            msg = entities.get("message", "")
            resp = f"Sending message to {contact}: '{msg}'." if msg else f"Opening message chat with {contact}."
            return CommandResult(
                command_id, intent, True,
                spoken_response=resp,
                plugin_used="SMSHandler",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent in (BuiltInIntent.OPEN_APP, BuiltInIntent.PLAY_YOUTUBE, BuiltInIntent.PLAY_SPOTIFY, BuiltInIntent.OPEN_CAMERA, BuiltInIntent.OPEN_BROWSER, BuiltInIntent.OPEN_SETTINGS, BuiltInIntent.OPEN_GALLERY):
            app = entities.get("app") or entities.get("query") or intent.value.replace("OPEN_", "").lower()
            return CommandResult(
                command_id, intent, True,
                spoken_response=f"Opening {app}.",
                plugin_used="AppLauncherHandler",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == BuiltInIntent.FLASHLIGHT_ON:
            return CommandResult(
                command_id, intent, True,
                spoken_response="Flashlight turned on.",
                plugin_used="FlashlightHandler",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == BuiltInIntent.FLASHLIGHT_OFF:
            return CommandResult(
                command_id, intent, True,
                spoken_response="Flashlight turned off.",
                plugin_used="FlashlightHandler",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == BuiltInIntent.SET_VOLUME:
            percent = entities.get("percentage", "50")
            return CommandResult(
                command_id, intent, True,
                spoken_response=f"Volume set to {percent} percent.",
                plugin_used="VolumeHandler",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == BuiltInIntent.SET_BRIGHTNESS:
            percent = entities.get("percentage", "70")
            return CommandResult(
                command_id, intent, True,
                spoken_response=f"Brightness set to {percent} percent.",
                plugin_used="BrightnessHandler",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        elif intent == BuiltInIntent.BATTERY_STATUS:
            return CommandResult(
                command_id, intent, True,
                spoken_response="Battery level is 85 percent, healthy.",
                plugin_used="DeviceInfoPlugin",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        else:
            return CommandResult(
                command_id, intent, False,
                spoken_response="Sorry, I didn't recognize that command.",
                plugin_used="None",
                entities=entities,
                execution_time_ms=int((time.time() - start_time) * 1000),
                error_message="Unknown Intent"
            )
