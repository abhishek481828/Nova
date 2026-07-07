import unittest
from unittest.mock import MagicMock, patch
import time

from nova.core.memory import WorkingMemory, SessionState, Interaction, reset_working_memory
from nova.browser.manager import BrowserManager

class TestBrowserMemory(unittest.TestCase):
    def setUp(self):
        self.wm = reset_working_memory()
        # Ensure BrowserManager working memory is reset/set to our test instance
        BrowserManager._working_memory = self.wm

    def tearDown(self):
        BrowserManager._working_memory = None
        BrowserManager.close_connection()

    def test_validation_constraints(self):
        # Verify valid fields do not throw
        session = SessionState(
            open_tabs_count=3,
            navigation_history=["https://google.com"],
            download_activity=[{"filename": "test.txt", "url": "https://test.com/file"}]
        )
        self.assertEqual(session.open_tabs_count, 3)

        # Verify invalid open_tabs_count raises ValueError
        with self.assertRaises(ValueError):
            SessionState(open_tabs_count=-1)

        # Verify invalid type for open_tabs_count raises ValueError
        with self.assertRaises(ValueError):
            SessionState(open_tabs_count="invalid")

        # Verify invalid navigation_history type raises TypeError
        with self.assertRaises(TypeError):
            SessionState(navigation_history="not-a-list")

        # Verify invalid elements in navigation_history raises TypeError
        with self.assertRaises(TypeError):
            SessionState(navigation_history=["valid", 123])

        # Verify invalid download_activity type raises TypeError
        with self.assertRaises(TypeError):
            SessionState(download_activity="not-a-list")

        # Verify invalid elements in download_activity raises TypeError
        with self.assertRaises(TypeError):
            SessionState(download_activity=[{"filename": "test.txt"}, "invalid"])

    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    def test_update_browser_memory_state_not_running(self, mock_is_running):
        mock_is_running.return_value = False
        
        # Seed working memory with some browser values
        self.wm.set("current_browser", "Chromium")
        self.wm.set("open_tabs_count", 5)

        # Execute
        BrowserManager.update_browser_memory_state(self.wm)

        # Assert reset values
        self.assertIsNone(self.wm.get("current_browser"))
        self.assertEqual(self.wm.get("open_tabs_count"), 0)
        self.assertIsNone(self.wm.get("current_url"))

    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    @patch("nova.browser.manager.BrowserManager.get_browser")
    def test_update_browser_memory_state_running(self, mock_get_browser, mock_is_running):
        mock_is_running.return_value = True

        # Mock Page
        mock_page = MagicMock()
        mock_page.title.return_value = "Google Search"
        mock_page.url = "https://www.google.com/search?q=nova+ai+assistant"
        
        # Mock Context
        mock_context = MagicMock()
        mock_context.pages = [mock_page]

        # Mock Browser
        mock_browser = MagicMock()
        mock_browser.contexts = [mock_context]
        mock_get_browser.return_value = mock_browser

        # Run state update
        BrowserManager.update_browser_memory_state(self.wm)

        # Assert correct field mappings
        self.assertEqual(self.wm.get("current_browser"), "Chromium")
        self.assertEqual(self.wm.get("open_tabs_count"), 1)
        self.assertEqual(self.wm.get("tab_title"), "Google Search")
        self.assertEqual(self.wm.get("current_url"), "https://www.google.com/search?q=nova+ai+assistant")
        self.assertEqual(self.wm.get("domain"), "www.google.com")
        self.assertEqual(self.wm.get("search_engine"), "Google")
        self.assertEqual(self.wm.get("current_search_query"), "nova ai assistant")

    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    @patch("nova.browser.manager.BrowserManager.get_browser")
    def test_navigation_history_no_duplicates(self, mock_get_browser, mock_is_running):
        mock_is_running.return_value = True

        # Mock Page
        mock_page = MagicMock()
        mock_page.title.return_value = "GitHub"
        mock_page.url = "https://github.com"
        
        # Mock Context
        mock_context = MagicMock()
        mock_context.pages = [mock_page]

        # Mock Browser
        mock_browser = MagicMock()
        mock_browser.contexts = [mock_context]
        mock_get_browser.return_value = mock_browser

        # Run first time
        BrowserManager.update_browser_memory_state(self.wm)
        history_1 = list(self.wm.get("navigation_history"))
        self.assertEqual(history_1, ["https://github.com"])

        # Run second time with same URL
        BrowserManager.update_browser_memory_state(self.wm)
        history_2 = list(self.wm.get("navigation_history"))
        # Should not append duplicate
        self.assertEqual(history_2, ["https://github.com"])

        # Navigate to a new URL
        mock_page.url = "https://github.com/trending"
        BrowserManager.update_browser_memory_state(self.wm)
        history_3 = list(self.wm.get("navigation_history"))
        self.assertEqual(history_3, ["https://github.com", "https://github.com/trending"])

    def test_handle_download_event(self):
        mock_download = MagicMock()
        mock_download.url = "https://example.com/installer.dmg"
        mock_download.suggested_filename = "installer.dmg"

        # Record first download
        BrowserManager._handle_download(mock_download)
        downloads = self.wm.get("download_activity")
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0]["filename"], "installer.dmg")
        self.assertEqual(downloads[0]["url"], "https://example.com/installer.dmg")

        # Record same download (should not duplicate)
        BrowserManager._handle_download(mock_download)
        downloads_after = self.wm.get("download_activity")
        self.assertEqual(len(downloads_after), 1)

    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    @patch("nova.browser.manager.BrowserManager.get_browser")
    def test_search_queries_parsing(self, mock_get_browser, mock_is_running):
        mock_is_running.return_value = True

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_browser = MagicMock()
        mock_browser.contexts = [mock_context]
        mock_get_browser.return_value = mock_browser

        # Google Search
        mock_page.url = "https://www.google.co.in/search?q=test+query+here&oq=test"
        BrowserManager.update_browser_memory_state(self.wm)
        self.assertEqual(self.wm.get("search_engine"), "Google")
        self.assertEqual(self.wm.get("current_search_query"), "test query here")

        # Bing Search
        mock_page.url = "https://www.bing.com/search?q=bing+search+term"
        BrowserManager.update_browser_memory_state(self.wm)
        self.assertEqual(self.wm.get("search_engine"), "Bing")
        self.assertEqual(self.wm.get("current_search_query"), "bing search term")

        # DuckDuckGo Search
        mock_page.url = "https://duckduckgo.com/?q=ddg+query"
        BrowserManager.update_browser_memory_state(self.wm)
        self.assertEqual(self.wm.get("search_engine"), "DuckDuckGo")
        self.assertEqual(self.wm.get("current_search_query"), "ddg query")

        # Yahoo Search
        mock_page.url = "https://search.yahoo.com/search?p=yahoo+query"
        BrowserManager.update_browser_memory_state(self.wm)
        self.assertEqual(self.wm.get("search_engine"), "Yahoo")
        self.assertEqual(self.wm.get("current_search_query"), "yahoo query")

if __name__ == "__main__":
    unittest.main()
