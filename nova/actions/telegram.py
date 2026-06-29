from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.telegram import TelegramService

class TelegramAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "telegram"

    def execute(self, params: Dict[str, Any]) -> str:
        message = params.get("message", "").strip()

        if not message:
            return "Error: No message content provided to send via Telegram."

        try:
            service = TelegramService()
            success = service.send_message(message)
            if success:
                return f"Message sent to your Telegram chat successfully: '{message}'"
            else:
                return "Failed to send message via Telegram. Check logs for details."
        except Exception as e:
            return f"Telegram action failed: {e}"
