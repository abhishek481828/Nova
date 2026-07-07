import unittest
from unittest.mock import MagicMock, patch
from nova.browser.chatgpt_manager import ChatGPTManager
from nova.ai.prompt_validator import PromptValidator

class TestChatGPTConversationMode(unittest.TestCase):
    def setUp(self):
        # Reset ChatGPTManager state before each test
        ChatGPTManager._chatgpt_page = None
        ChatGPTManager._textarea_locator = None
        ChatGPTManager._send_button_locator = None
        ChatGPTManager._container_locator = None
        ChatGPTManager._last_response_locator = None
        ChatGPTManager._initialized = False
        ChatGPTManager._working_memory = None

    def _setup_runner_mocks(self, mock_runner):
        # Mock BrowserRunner execute to run directly
        mock_runner.execute.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
        
        # Mock BrowserRunner submit to execute directly and return mock Future
        def submit_side_effect(fn, *args, **kwargs):
            future = MagicMock()
            try:
                res = fn(*args, **kwargs)
                future.result.return_value = res
            except Exception as e:
                future.result.side_effect = e
            return future
        mock_runner.submit.side_effect = submit_side_effect

    @patch("nova.browser.chatgpt_manager.BrowserRunner")
    def test_conversation_persistence_and_no_reload(self, mock_runner):
        # Setup cached page and verify no reloads
        mock_page = MagicMock()
        mock_page.url = "https://chatgpt.com/c/active-conv-id"
        
        ChatGPTManager._chatgpt_page = mock_page
        ChatGPTManager._textarea_locator = MagicMock()
        ChatGPTManager._send_button_locator = MagicMock()
        ChatGPTManager._last_response_locator = MagicMock()
        ChatGPTManager._last_response_locator.inner_text.return_value = "Response content"
        ChatGPTManager._initialized = True

        self._setup_runner_mocks(mock_runner)

        with patch.object(mock_page, "goto") as mock_goto:
            # Query 1
            res1 = ChatGPTManager.execute_workflow("ask", "tell me a joke")
            self.assertEqual(res1, "Response content")
            
            # Query 2 (consecutive)
            res2 = ChatGPTManager.execute_workflow("ask", "explain the joke")
            self.assertEqual(res2, "Response content")
            
            # Verify browser reload/navigation was never called (persistence checks)
            mock_goto.assert_not_called()
            self.assertEqual(ChatGPTManager._chatgpt_page, mock_page)

    def test_follow_up_commands_bypass_enhancement(self):
        # Direct verification of validator bypasses
        continuation_shortcuts = [
            "continue", "explain more", "summarize", "simplify", "give example",
            "new chat", "start a new chat", "clear chat"
        ]
        for prompt in continuation_shortcuts:
            self.assertTrue(PromptValidator.is_simple(prompt), f"'{prompt}' should bypass enhancement")
            self.assertTrue(PromptValidator.is_simple(f"  {prompt}  "), f"spaced '{prompt}' should bypass")

    @patch("nova.browser.chatgpt_manager.BrowserRunner")
    def test_new_chat_resets_context(self, mock_runner):
        mock_page = MagicMock()
        mock_page.url = "https://chatgpt.com/c/old-id"
        
        ChatGPTManager._chatgpt_page = mock_page
        ChatGPTManager._textarea_locator = MagicMock()
        ChatGPTManager._send_button_locator = MagicMock()
        ChatGPTManager._last_response_locator = MagicMock()
        ChatGPTManager._initialized = True

        self._setup_runner_mocks(mock_runner)

        with patch.object(mock_page, "goto") as mock_goto:
            result = ChatGPTManager.execute_workflow("new_chat", "")
            
            self.assertEqual(result, "Started a new ChatGPT conversation.")
            # Verify navigation resets to the base URL
            mock_goto.assert_called_once_with("https://chatgpt.com", timeout=30000)
