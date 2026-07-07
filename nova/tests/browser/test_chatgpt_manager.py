import unittest
from unittest.mock import MagicMock, patch
from nova.browser.chatgpt_manager import ChatGPTManager

class TestChatGPTManager(unittest.TestCase):
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
        # Emulate BrowserRunner execute
        mock_runner.execute.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
        
        # Emulate BrowserRunner submit returning a mock Future
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
    @patch("nova.browser.chatgpt_manager.BrowserManager")
    def test_startup_initialization(self, mock_manager, mock_runner):
        # Setup mocks
        mock_page = MagicMock()
        mock_page.url = "https://chatgpt.com"
        
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        
        mock_manager.ensure_browser.return_value = True
        mock_manager.get_browser.return_value = mock_browser
        mock_manager.get_persistent_context.return_value = mock_context

        self._setup_runner_mocks(mock_runner)

        ChatGPTManager._initialize_in_runner()
        
        self.assertTrue(ChatGPTManager._initialized)
        self.assertEqual(ChatGPTManager._chatgpt_page, mock_page)
        self.assertIsNotNone(ChatGPTManager._textarea_locator)
        self.assertIsNotNone(ChatGPTManager._send_button_locator)

    @patch("nova.browser.chatgpt_manager.BrowserRunner")
    @patch("nova.browser.chatgpt_manager.PromptEnhancer")
    def test_execute_workflow_simple_bypass(self, mock_enhancer_class, mock_runner):
        # Setup page crash recovery bypass
        ChatGPTManager._chatgpt_page = MagicMock()
        ChatGPTManager._chatgpt_page.url = "https://chatgpt.com"
        ChatGPTManager._textarea_locator = MagicMock()
        ChatGPTManager._send_button_locator = MagicMock()
        ChatGPTManager._last_response_locator = MagicMock()
        ChatGPTManager._last_response_locator.inner_text.return_value = "10"
        
        self._setup_runner_mocks(mock_runner)

        # Execute simple query: should not trigger enhancement
        result = ChatGPTManager.execute_workflow("ask", "what is 5+5")
        
        self.assertEqual(result, "10")
        mock_enhancer_class.assert_not_called()

    @patch("nova.browser.chatgpt_manager.BrowserRunner")
    @patch("nova.browser.chatgpt_manager.PromptEnhancer")
    def test_execute_workflow_complex_enhancement(self, mock_enhancer_class, mock_runner):
        # Mock Enhancer
        mock_enhancer = MagicMock()
        mock_enhancer.enhance.return_value = "Please write a quicksort in python."
        mock_enhancer_class.return_value = mock_enhancer

        # Mock page
        ChatGPTManager._chatgpt_page = MagicMock()
        ChatGPTManager._chatgpt_page.url = "https://chatgpt.com"
        ChatGPTManager._textarea_locator = MagicMock()
        ChatGPTManager._send_button_locator = MagicMock()
        ChatGPTManager._last_response_locator = MagicMock()
        ChatGPTManager._last_response_locator.inner_text.return_value = "Quicksort implementation..."

        self._setup_runner_mocks(mock_runner)

        # Complex query
        result = ChatGPTManager.execute_workflow("ask", "write quicksort in python")

        self.assertEqual(result, "Quicksort implementation...")
        mock_enhancer.enhance.assert_called_once_with("write quicksort in python")

    @patch("nova.browser.chatgpt_manager.BrowserRunner")
    def test_execute_workflow_new_chat(self, mock_runner):
        # Setup page
        ChatGPTManager._chatgpt_page = MagicMock()
        
        self._setup_runner_mocks(mock_runner)
        
        with patch.object(ChatGPTManager._chatgpt_page, "goto") as mock_goto:
            result = ChatGPTManager.execute_workflow("new_chat", "")
            self.assertEqual(result, "Started a new ChatGPT conversation.")
            mock_goto.assert_called_once_with("https://chatgpt.com", timeout=30000)

    @patch("nova.browser.chatgpt_manager.BrowserRunner")
    @patch("nova.browser.chatgpt_manager.BrowserManager")
    def test_tab_crash_recovery_trigger(self, mock_manager, mock_runner):
        # Cached page url lookup throws target closed exception
        bad_page = MagicMock()
        type(bad_page).url = property(MagicMock(side_effect=Exception("Target closed")))
        
        # New valid page
        new_page = MagicMock()
        new_page.url = "https://chatgpt.com"
        
        ChatGPTManager._chatgpt_page = bad_page
        ChatGPTManager._initialized = True
        
        # Mock setup for re-initialization
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = []
        mock_context.new_page.return_value = new_page
        
        mock_manager.ensure_browser.return_value = True
        mock_manager.get_browser.return_value = mock_browser
        mock_manager.get_persistent_context.return_value = mock_context

        self._setup_runner_mocks(mock_runner)

        # Verify recovery trigger
        ChatGPTManager._verify_and_recover_in_runner()
        
        self.assertEqual(ChatGPTManager._chatgpt_page, new_page)
        self.assertTrue(ChatGPTManager._initialized)
