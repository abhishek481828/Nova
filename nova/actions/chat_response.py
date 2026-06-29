from typing import Any, Dict
from nova.actions.base import BaseAction

class ChatResponseAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "chat_response"

    def execute(self, params: Dict[str, Any]) -> str:
        # Simply return the chat text message
        message = params.get("message", "").strip()
        if not message:
            return "I'm Nova, your assistant. I am ready to process commands."
        return message
