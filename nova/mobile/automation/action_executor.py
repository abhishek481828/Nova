"""ActionExecutor — Runs automation actions sequentially via CommandEngine."""

import time
import logging
from typing import List, Optional
from nova.mobile.automation.models import AutomationAction
from nova.mobile.automation.enums import ActionType

logger = logging.getLogger("nova.mobile.automation.action_executor")


ACTION_TEXT_MAP = {
    ActionType.FLASHLIGHT_ON:     lambda p: "Turn on flashlight",
    ActionType.FLASHLIGHT_OFF:    lambda p: "Turn off flashlight",
    ActionType.PLAY_YOUTUBE:      lambda p: "Open YouTube",
    ActionType.PLAY_MUSIC:        lambda p: "Play music",
    ActionType.OPEN_CAMERA:       lambda p: "Open camera",
    ActionType.OPEN_GALLERY:      lambda p: "Open gallery",
    ActionType.ENABLE_BLUETOOTH:  lambda p: "Enable Bluetooth",
    ActionType.DISABLE_BLUETOOTH: lambda p: "Disable Bluetooth",
    ActionType.ENABLE_DND:        lambda p: "Enable Do Not Disturb",
    ActionType.DISABLE_DND:       lambda p: "Disable Do Not Disturb",
    ActionType.CALL_CONTACT:      lambda p: f"Call {p.get('contact', 'unknown')}",
    ActionType.SEND_SMS:          lambda p: f"Send message to {p.get('contact', 'unknown')} saying {p.get('message', '')}",
    ActionType.OPEN_APP:          lambda p: f"Open {p.get('app', 'app')}",
    ActionType.SET_BRIGHTNESS:    lambda p: f"Set brightness to {p.get('value', '50')}%",
    ActionType.SET_VOLUME:        lambda p: f"Set volume to {p.get('value', '50')}%",
    ActionType.SET_ALARM:         lambda p: f"Set alarm for {p.get('time', '7:00 AM')}",
    ActionType.SET_TIMER:         lambda p: f"Set timer for {p.get('minutes', '10')} minutes",
    ActionType.COPY_TEXT:         lambda p: f"Copy {p.get('text', '')}",
    ActionType.SHOW_NOTIFICATION: lambda p: f"Show notification {p.get('message', '')}",
    ActionType.NOVA_CORE_REQUEST: lambda p: p.get('request', 'Nova Core request'),
    ActionType.WAIT_SECONDS:      lambda p: "Wait",
}


class ActionLog:
    def __init__(self, action_type: str, is_success: bool,
                 spoken_response: str, error_message: Optional[str] = None,
                 duration_ms: int = 0):
        self.action_type = action_type
        self.is_success = is_success
        self.spoken_response = spoken_response
        self.error_message = error_message
        self.duration_ms = duration_ms


class ActionExecutor:
    def __init__(self, command_engine=None):
        self.command_engine = command_engine

    def execute(self, actions: List[AutomationAction]) -> List[ActionLog]:
        logs = []
        for action in actions:
            start = time.time()
            cmd_text = self._build_text(action)
            logger.info(f"Executing: {action.type} → \"{cmd_text}\"")

            try:
                if self.command_engine and action.type != ActionType.WAIT_SECONDS:
                    result = self.command_engine.execute_text(cmd_text)
                    log = ActionLog(
                        action_type=action.type.value,
                        is_success=result.is_success,
                        spoken_response=result.spoken_response,
                        error_message=result.error_message,
                        duration_ms=int((time.time() - start) * 1000)
                    )
                else:
                    # WAIT_SECONDS or no engine → simulate
                    wait = action.delay_seconds_after or int(action.params.get("seconds", 0))
                    if wait > 0:
                        time.sleep(min(wait, 5))  # cap test waits at 5s
                    log = ActionLog(action.type.value, True, f"Executed {action.type.value}",
                                   duration_ms=int((time.time() - start) * 1000))
            except Exception as e:
                logger.error(f"Action {action.type} failed: {e}", exc_info=True)
                log = ActionLog(action.type.value, False, "",
                                error_message=str(e),
                                duration_ms=int((time.time() - start) * 1000))
            logs.append(log)

            if action.delay_seconds_after > 0 and action.type != ActionType.WAIT_SECONDS:
                time.sleep(min(action.delay_seconds_after, 2))  # cap in tests

        return logs

    def _build_text(self, action: AutomationAction) -> str:
        builder = ACTION_TEXT_MAP.get(action.type)
        return builder(action.params) if builder else action.type.value
