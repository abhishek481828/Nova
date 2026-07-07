import logging
from typing import Optional
from nova.browser.providers.base import AIProvider
from nova.browser.chatgpt_manager import ChatGPTManager

logger = logging.getLogger("nova.browser.providers.chatgpt")

class ChatGPTProvider(AIProvider):
    """
    Playwright-based ChatGPT AI Provider.
    Implements the generic AIProvider interface by delegating directly
    to the core ChatGPTManager implementation.
    """
    
    @classmethod
    def initialize(cls) -> None:
        """Warms up and prepares the ChatGPT tab in the background."""
        ChatGPTManager._initialize_on_startup_implementation()

    @classmethod
    def execute_action(cls, operation: str, prompt: str) -> str:
        """Executes the action using the core workflow implementation."""
        return ChatGPTManager._execute_workflow_implementation(operation, prompt)

    @classmethod
    def reset_session(cls) -> None:
        """Resets the active ChatGPT conversation."""
        from nova.browser.runner import BrowserRunner
        BrowserRunner.execute(ChatGPTManager._reset_chat_in_runner)

    @classmethod
    def close(cls) -> None:
        """Closes and releases active Playwright connection resources."""
        from nova.browser.manager import BrowserManager
        BrowserManager.close_connection()
        ChatGPTManager._initialized = False
        ChatGPTManager._chatgpt_page = None

# Automatically register ChatGPTProvider as the default active provider in ChatGPTManager
ChatGPTManager._active_provider = ChatGPTProvider
