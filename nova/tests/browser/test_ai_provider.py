import unittest
from unittest.mock import MagicMock
from nova.browser.providers.base import AIProvider
from nova.browser.providers.chatgpt import ChatGPTProvider
from nova.browser.chatgpt_manager import ChatGPTManager

class MockAIProvider(AIProvider):
    _chatgpt_page = "mock_page"
    _initialized = True
    _textarea_locator = None
    _send_button_locator = None
    _container_locator = None
    _last_response_locator = None
    _working_memory = None
    _last_received_response = "mock_response"

    @classmethod
    def initialize(cls) -> None:
        cls._initialized = True

    @classmethod
    def execute_action(cls, operation: str, prompt: str) -> str:
        return f"Mock output: {operation} - {prompt}"

    @classmethod
    def reset_session(cls) -> None:
        pass

    @classmethod
    def close(cls) -> None:
        cls._initialized = False

class TestAIProviderArchitecture(unittest.TestCase):
    def test_provider_subclassing(self):
        self.assertTrue(issubclass(ChatGPTProvider, AIProvider))
        self.assertTrue(issubclass(MockAIProvider, AIProvider))

    def test_delegation_metaclass(self):
        # Swap manager provider to MockAIProvider
        original_provider = ChatGPTManager._active_provider
        ChatGPTManager._active_provider = MockAIProvider

        try:
            # 1. Attribute reading delegation
            self.assertEqual(ChatGPTManager._chatgpt_page, "mock_page")
            self.assertEqual(ChatGPTManager._last_received_response, "mock_response")
            self.assertTrue(ChatGPTManager._initialized)

            # 2. Attribute writing delegation
            ChatGPTManager._last_received_response = "new_mock_val"
            self.assertEqual(MockAIProvider._last_received_response, "new_mock_val")

            # 3. Method execution delegation
            res = ChatGPTManager.execute_workflow("ask", "hello")
            self.assertEqual(res, "Mock output: ask - hello")
        finally:
            # Restore provider
            ChatGPTManager._active_provider = original_provider
            
    def test_default_chatgpt_provider_active(self):
        self.assertEqual(ChatGPTManager._active_provider, ChatGPTProvider)
