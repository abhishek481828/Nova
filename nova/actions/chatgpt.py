import logging
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.browser.chatgpt_manager import ChatGPTManager

logger = logging.getLogger("nova.actions.chatgpt")

class ChatGPTAction(BaseAction):
    """
    Nova Action to interact with ChatGPT.
    Delegates all coordination and execution to ChatGPTManager.
    """
    @property
    def action_name(self) -> str:
        return "chatgpt_action"

    @property
    def is_long_running(self) -> bool:
        return True

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "open").strip().lower()
        prompt = params.get("prompt") or params.get("value") or params.get("query") or ""
        
        if operation == "translate_response":
            prompt = params.get("language") or prompt or "Spanish"
            
        # Propagate working memory to ChatGPTManager
        if hasattr(self, "working_memory") and self.working_memory is not None:
            ChatGPTManager._working_memory = self.working_memory

        result = ChatGPTManager.execute_workflow(operation, prompt)
        return result
