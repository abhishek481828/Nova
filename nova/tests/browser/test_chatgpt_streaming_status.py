import sys
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch
from nova.browser.chatgpt_manager import ChatGPTManager

class TestChatGPTStreamingStatus(unittest.TestCase):
    def setUp(self):
        ChatGPTManager._chatgpt_page = None
        ChatGPTManager._textarea_locator = None
        ChatGPTManager._send_button_locator = None
        ChatGPTManager._container_locator = None
        ChatGPTManager._last_response_locator = None
        ChatGPTManager._initialized = False
        ChatGPTManager._working_memory = None

    def _setup_runner_mocks(self, mock_runner):
        # Mock BrowserRunner execute and submit
        mock_runner.execute.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
        
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
    @patch("nova.browser.chatgpt_manager.PromptEnhancer")
    def test_streaming_status_order_complex_prompt(self, mock_enhancer_class, mock_runner):
        # Setup mocks
        mock_enhancer = MagicMock()
        mock_enhancer.enhance.return_value = "quicksort in python"
        mock_enhancer_class.return_value = mock_enhancer
        
        ChatGPTManager._chatgpt_page = MagicMock()
        ChatGPTManager._chatgpt_page.url = "https://chatgpt.com"
        ChatGPTManager._textarea_locator = MagicMock()
        ChatGPTManager._send_button_locator = MagicMock()
        ChatGPTManager._last_response_locator = MagicMock()
        ChatGPTManager._last_response_locator.inner_text.return_value = "Code implementation..."

        self._setup_runner_mocks(mock_runner)

        # Capture stdout
        captured_output = StringIO()
        sys.stdout = captured_output

        try:
            # Complex prompt to trigger "Improving prompt..."
            result = ChatGPTManager.execute_workflow("ask", "write quicksort in python")
        finally:
            # Restore stdout
            sys.stdout = sys.__stdout__

        self.assertEqual(result, "Code implementation...")
        
        output_text = captured_output.getvalue()
        lines = [line.strip() for line in output_text.split("\n") if line.strip()]

        expected_order = [
            "Improving prompt...",
            "Opening ChatGPT...",
            "Sending...",
            "Waiting...",
            "Response received..."
        ]

        # Verify correct order
        current_index = 0
        for line in lines:
            if line == expected_order[current_index]:
                current_index += 1
                if current_index == len(expected_order):
                    break

        self.assertEqual(
            current_index, 
            len(expected_order), 
            f"Status updates did not match expected order. Received lines: {lines}"
        )

    @patch("nova.browser.chatgpt_manager.BrowserRunner")
    @patch("nova.browser.chatgpt_manager.PromptEnhancer")
    def test_streaming_status_order_simple_prompt(self, mock_enhancer_class, mock_runner):
        ChatGPTManager._chatgpt_page = MagicMock()
        ChatGPTManager._chatgpt_page.url = "https://chatgpt.com"
        ChatGPTManager._textarea_locator = MagicMock()
        ChatGPTManager._send_button_locator = MagicMock()
        ChatGPTManager._last_response_locator = MagicMock()
        ChatGPTManager._last_response_locator.inner_text.return_value = "10"

        self._setup_runner_mocks(mock_runner)

        captured_output = StringIO()
        sys.stdout = captured_output

        try:
            # Simple prompt - skips "Improving prompt..."
            result = ChatGPTManager.execute_workflow("ask", "what is 5+5")
        finally:
            sys.stdout = sys.__stdout__

        self.assertEqual(result, "10")
        
        output_text = captured_output.getvalue()
        lines = [line.strip() for line in output_text.split("\n") if line.strip()]

        # "Improving prompt..." should not be in the output for simple queries
        self.assertNotIn("Improving prompt...", lines)
        
        expected_order = [
            "Opening ChatGPT...",
            "Sending...",
            "Waiting...",
            "Response received..."
        ]

        current_index = 0
        for line in lines:
            if line == expected_order[current_index]:
                current_index += 1
                if current_index == len(expected_order):
                    break

        self.assertEqual(
            current_index, 
            len(expected_order), 
            f"Simple query status updates did not match expected order. Received lines: {lines}"
        )
