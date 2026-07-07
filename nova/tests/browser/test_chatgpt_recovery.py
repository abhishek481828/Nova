import unittest
from unittest.mock import MagicMock, patch
from nova.browser.chatgpt_manager import ChatGPTManager

class TestChatGPTRecovery(unittest.TestCase):
    def setUp(self):
        ChatGPTManager._chatgpt_page = None
        ChatGPTManager._initialized = False

    @patch("nova.browser.chatgpt_manager.ChatGPTManager._initialize_in_runner_with_retries")
    @patch("nova.browser.manager.BrowserManager.get_browser")
    def test_recover_closed_tab(self, mock_get_browser, mock_init_retries):
        # 1. Simulate browser is connected but page URL raises exception (e.g. closed tab)
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_get_browser.return_value = mock_browser

        mock_page = MagicMock()
        type(mock_page).url = property(MagicMock(side_effect=Exception("Target page closed")))
        ChatGPTManager._chatgpt_page = mock_page

        # Run recovery check
        ChatGPTManager._verify_and_recover_in_runner()

        # Verify that initialization with retries was called
        mock_init_retries.assert_called_once()
        self.assertFalse(ChatGPTManager._initialized)

    @patch("nova.browser.chatgpt_manager.ChatGPTManager._initialize_in_runner_with_retries")
    @patch("nova.browser.manager.BrowserManager.close_connection")
    @patch("nova.browser.manager.BrowserManager.get_browser")
    def test_recover_browser_crash(self, mock_get_browser, mock_close_connection, mock_init_retries):
        # 2. Simulate browser is NOT connected (e.g. crash/disconnect)
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = False
        mock_get_browser.return_value = mock_browser

        ChatGPTManager._chatgpt_page = MagicMock()

        # Run recovery check
        ChatGPTManager._verify_and_recover_in_runner()

        # Verify that BrowserManager.close_connection was called to clean up context,
        # and new initialization with retries was triggered
        mock_close_connection.assert_called_once()
        mock_init_retries.assert_called_once()
        self.assertFalse(ChatGPTManager._initialized)

    @patch("nova.browser.manager.BrowserManager.get_browser")
    def test_recover_expired_session(self, mock_get_browser):
        # 3. Simulate browser connected but page redirected to login url
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_get_browser.return_value = mock_browser

        mock_page = MagicMock()
        type(mock_page).url = property(MagicMock(return_value="https://chatgpt.com/auth/login"))
        
        # Mock buttons to be not visible
        login_btn = MagicMock()
        login_btn.is_visible.return_value = False
        mock_page.locator.return_value.first = login_btn
        
        ChatGPTManager._chatgpt_page = mock_page
        ChatGPTManager._initialized = True

        # Run recovery check
        ChatGPTManager._verify_and_recover_in_runner()

        # Verify that it attempted to navigate back to chatgpt home to recover cookies
        mock_page.goto.assert_called_once_with("https://chatgpt.com", timeout=15000)
        mock_page.wait_for_load_state.assert_called_once_with("domcontentloaded", timeout=10000)
