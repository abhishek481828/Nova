import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from nova.browser.actions import ChromiumAction
from nova.browser.manager import BrowserManager

class NovaBrowserTestCase(unittest.TestCase):
    def setUp(self):
        BrowserManager.close_connection()
        self.playwright_patcher = patch("nova.browser.manager.sync_playwright")
        self.mock_sync_playwright = self.playwright_patcher.start()
        self.mock_playwright = MagicMock()
        self.mock_sync_playwright.return_value.start.return_value = self.mock_playwright
        self.mock_sync_playwright.return_value.__enter__.return_value = self.mock_playwright
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.playwright_patcher.stop()
        BrowserManager.close_connection()

class TestChromiumAction(NovaBrowserTestCase):

    @patch("nova.browser.actions.run_automation")
    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    def test_chromium_action_open(self, mock_is_browser_running, mock_run_automation):
        # 1. DevTools readiness check returns True
        mock_is_browser_running.return_value = True
        
        # 2. Mock run_automation to return success dict
        mock_run_automation.return_value = {"status": "success", "message": "Successfully navigated to youtube.com"}
        
        action = ChromiumAction()
        result = action.execute({"operation": "open", "url": "youtube.com"})
        
        self.assertEqual(result, "✅ Successfully navigated to youtube.com")
        mock_run_automation.assert_called_once_with({"operation": "open", "url": "https://youtube.com"})

    @patch("socket.socket")
    @patch("subprocess.Popen")
    @patch("nova.browser.manager.BrowserManager.is_cdp_ready")
    @patch("nova.browser.manager.BrowserManager.is_devtools_http_ready")
    @patch("nova.browser.manager.BrowserManager.is_process_alive")
    def test_chromium_action_launch_and_open(self, mock_is_process_alive, mock_is_devtools_http_ready, mock_is_cdp_ready, mock_popen, mock_socket):
        # Mock individual stage readiness check
        mock_is_process_alive.return_value = True
        mock_is_devtools_http_ready.return_value = True
        mock_is_cdp_ready.side_effect = [False, False, True]
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        # Prevent actual network check from claiming the port is in use
        mock_socket.return_value.__enter__.return_value.connect.side_effect = ConnectionRefusedError()
        
        res = BrowserManager.launch_browser()
        
        self.assertTrue(res)
        mock_popen.assert_called_once()

from nova.browser.actions import BrowserAction
from nova.actions.open_app import OpenAppAction

class TestDedicatedBrowserActions(NovaBrowserTestCase):

    @patch("nova.browser.actions.webbrowser.open")
    def test_browser_action_opens_default_browser(self, mock_webbrowser_open):
        mock_webbrowser_open.return_value = True
        
        action = BrowserAction()
        result = action.execute({"url": "example.com"})
        
        self.assertIn("Successfully opened default browser", result)
        mock_webbrowser_open.assert_called_once_with("https://example.com")

    @patch("nova.browser.manager.BrowserManager.focus_active_window")
    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    @patch("nova.core.executor.CommandExecutor.run_background")
    def test_open_app_action_already_running_focuses(self, mock_run_background, mock_is_browser_running, mock_focus_active_window):
        mock_is_browser_running.return_value = True
        mock_focus_active_window.return_value = True
        
        action = OpenAppAction()
        result = action.execute({"app": "chromium"})
        
        self.assertIn("focused existing chromium window", result)
        mock_is_browser_running.assert_called_once()
        mock_focus_active_window.assert_called_once()
        mock_run_background.assert_not_called()

    @patch("nova.browser.manager.BrowserManager.launch_browser")
    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    @patch("nova.core.executor.CommandExecutor.run_background")
    def test_open_app_action_not_running_launches(self, mock_run_background, mock_is_browser_running, mock_launch_browser):
        mock_is_browser_running.return_value = False
        mock_launch_browser.return_value = True
        
        action = OpenAppAction()
        result = action.execute({"app": "chromium"})
        
        self.assertIn("opened new chromium instance", result)
        mock_is_browser_running.assert_called_once()
        mock_launch_browser.assert_called_once()
        mock_run_background.assert_not_called()

    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    @patch("nova.core.executor.CommandExecutor.run_background")
    def test_open_app_action_launches_other_apps_normally(self, mock_run_background, mock_is_browser_running):
        mock_run_background.return_value = (0, "Success")
        
        action = OpenAppAction()
        result = action.execute({"app": "vlc"})
        
        self.assertIn("Successfully opened vlc", result)
        mock_is_browser_running.assert_not_called()
        mock_run_background.assert_called_once_with("vlc", shell=True)

    @patch("nova.browser.manager.sync_playwright")
    @patch("nova.browser.manager.BrowserManager.connect_browser")
    @patch("nova.browser.manager.BrowserManager.focus_browser")
    def test_focus_active_window_success(self, mock_focus_browser, mock_connect_browser, mock_sync_playwright):
        # Setup mocks
        mock_playwright_instance = MagicMock()
        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_instance
        
        mock_browser = MagicMock()
        mock_connect_browser.return_value = mock_browser
        
        mock_page_visible = MagicMock()
        mock_page_visible.evaluate.return_value = True
        mock_page_hidden = MagicMock()
        mock_page_hidden.evaluate.return_value = False
        
        mock_context = MagicMock()
        mock_context.pages = [mock_page_hidden, mock_page_visible]
        mock_browser.contexts = [mock_context]
        
        res = BrowserManager.focus_active_window()
        
        self.assertTrue(res)
        mock_focus_browser.assert_called_once_with(mock_page_visible)
        mock_browser.close.assert_not_called()

    @patch("nova.browser.manager.BrowserManager.restart_browser")
    @patch("nova.browser.manager.BrowserManager.wait_for_devtools")
    def test_connect_browser_recovery_success(self, mock_wait_for_devtools, mock_restart_browser):
        mock_wait_for_devtools.return_value = True
        
        mock_playwright = MagicMock()
        mock_chromium = mock_playwright.chromium
        mock_browser = MagicMock()
        mock_chromium.connect_over_cdp.side_effect = [Exception("ECONNRESET error"), mock_browser]
        
        res = BrowserManager.connect_browser(mock_playwright)
        
        self.assertEqual(res, mock_browser)
        mock_restart_browser.assert_called_once()
        self.assertEqual(mock_chromium.connect_over_cdp.call_count, 2)

    @patch("nova.browser.manager.BrowserManager.restart_browser")
    @patch("nova.browser.manager.BrowserManager.wait_for_devtools")
    def test_connect_browser_recovery_failure(self, mock_wait_for_devtools, mock_restart_browser):
        mock_wait_for_devtools.return_value = True
        
        mock_playwright = MagicMock()
        mock_chromium = mock_playwright.chromium
        mock_chromium.connect_over_cdp.side_effect = [Exception("ECONNRESET first"), Exception("ECONNRESET second")]
        
        with self.assertRaises(Exception) as context:
            BrowserManager.connect_browser(mock_playwright)
            
        self.assertIn("Failed to connect to Chromium after relaunch", str(context.exception))
        mock_restart_browser.assert_called_once()
        self.assertEqual(mock_chromium.connect_over_cdp.call_count, 2)

from nova.spelling import correct_action_data

class TestBrowserIntentRouting(NovaBrowserTestCase):

    def test_chrome_action_corrected_to_chromium_action(self):
        action_data = {"action": "chrome_action", "operation": "open", "url": "example.com"}
        corrected = correct_action_data(action_data, "open example.com")
        self.assertEqual(corrected["action"], "chromium_action")

    def test_browser_action_without_default_routed_to_chromium_action(self):
        action_data = {"action": "browser_action", "url": "example.com"}
        corrected = correct_action_data(action_data, "open example.com")
        self.assertEqual(corrected["action"], "chromium_action")
        self.assertEqual(corrected["operation"], "open")

    def test_browser_action_with_default_remains_browser_action(self):
        action_data = {"action": "browser_action", "url": "example.com"}
        corrected = correct_action_data(action_data, "open example.com in default browser")
        self.assertEqual(corrected["action"], "browser_action")
        self.assertNotIn("operation", corrected)

    def test_youtube_operation_aliases_resolve_to_search_youtube(self):
        for op in ("play_music", "music", "song", "play_song", "search_artist", "artist", "play_artist"):
            action_data = {"action": "chromium_action", "operation": op, "query": "test query"}
            corrected = correct_action_data(action_data, f"play {op} test query")
            self.assertEqual(corrected["operation"], "search_youtube")

from nova.browser.helper import run_automation

class TestBrowserContextAwareness(NovaBrowserTestCase):

    @patch("nova.browser.manager.BrowserManager.get_browser")
    def test_run_automation_delegates_to_github_context_handler(self, mock_get_browser):
        mock_browser = MagicMock()
        mock_get_browser.return_value = mock_browser
        
        mock_page = MagicMock()
        mock_page.url = "https://github.com/AbhishekDas/repository"
        mock_page.locator.return_value.is_visible.return_value = True
        
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_browser.contexts = [mock_context]
        
        # Call run_automation with github context query
        params = {"operation": "fill_form", "url": "google.com", "_user_query": "search nova-code"}
        result = run_automation(params)
        
        self.assertEqual(result["status"], "success")
        self.assertIn("Searched GitHub for: 'nova-code'", result["message"])
        mock_page.locator.assert_any_call("input#query-builder-test")
        mock_page.keyboard.press.assert_called_with("Enter")

    @patch("nova.browser.manager.BrowserManager.get_browser")
    def test_run_automation_delegates_to_chatgpt_context_handler(self, mock_get_browser):
        mock_browser = MagicMock()
        mock_get_browser.return_value = mock_browser
        
        mock_page = MagicMock()
        mock_page.url = "https://chatgpt.com/"
        
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_browser.contexts = [mock_context]
        
        # Call run_automation with ChatGPT context query
        params = {"operation": "fill_form", "url": "google.com", "_user_query": "ask tell me a joke"}
        result = run_automation(params)
        
        self.assertEqual(result["status"], "success")
        self.assertIn("Sent prompt to ChatGPT: 'tell me a joke'", result["message"])
        mock_page.locator.assert_any_call("#prompt-textarea")
        mock_page.locator.assert_any_call("[aria-label='Send prompt'], button[data-testid*='send'], Send")

class TestBrowserContextManagement(NovaBrowserTestCase):

    def test_get_persistent_context_empty_fallback_success(self):
        mock_browser = MagicMock()
        mock_browser.contexts = []
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context

        context = BrowserManager.get_persistent_context(mock_browser)
        self.assertEqual(context, mock_context)
        mock_browser.new_context.assert_called_once()

    def test_get_persistent_context_empty_fallback_failure(self):
        mock_browser = MagicMock()
        mock_browser.contexts = []
        mock_browser.new_context.side_effect = Exception("Failed to create context")

        with self.assertRaises(Exception) as ctx:
            BrowserManager.get_persistent_context(mock_browser)
        
        self.assertIn("Failed to create context", str(ctx.exception))

    def test_get_persistent_context_multiple_with_valid(self):
        mock_browser = MagicMock()
        mock_context_valid = MagicMock()
        mock_context_valid.pages = []
        mock_browser.contexts = [mock_context_valid]

        context = BrowserManager.get_persistent_context(mock_browser)
        self.assertEqual(context, mock_context_valid)
        mock_browser.new_context.assert_not_called()

    def test_get_persistent_context_multiple_first_invalid_second_valid(self):
        from unittest.mock import PropertyMock
        mock_browser = MagicMock()
        
        mock_context_invalid = MagicMock()
        type(mock_context_invalid).pages = PropertyMock(side_effect=Exception("Closed context"))
        
        mock_context_valid = MagicMock()
        mock_context_valid.pages = []
        
        mock_browser.contexts = [mock_context_invalid, mock_context_valid]

        context = BrowserManager.get_persistent_context(mock_browser)
        self.assertEqual(context, mock_context_valid)
        mock_browser.new_context.assert_not_called()

    def test_get_persistent_context_all_invalid_fallback_success(self):
        from unittest.mock import PropertyMock
        mock_browser = MagicMock()
        
        mock_context_invalid = MagicMock()
        type(mock_context_invalid).pages = PropertyMock(side_effect=Exception("Closed context"))
        mock_browser.contexts = [mock_context_invalid]
        
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context

        context = BrowserManager.get_persistent_context(mock_browser)
        self.assertEqual(context, mock_context)
        mock_browser.new_context.assert_called_once()

    def test_get_persistent_context_all_invalid_fallback_failure(self):
        from unittest.mock import PropertyMock
        mock_browser = MagicMock()
        
        mock_context_invalid = MagicMock()
        type(mock_context_invalid).pages = PropertyMock(side_effect=Exception("Closed context"))
        mock_browser.contexts = [mock_context_invalid]
        
        mock_browser.new_context.side_effect = Exception("Failed to create context")

        with self.assertRaises(Exception) as ctx:
            BrowserManager.get_persistent_context(mock_browser)
            
        self.assertIn("Failed to create context", str(ctx.exception))
        mock_browser.new_context.assert_called_once()

class TestBrowserRestart(NovaBrowserTestCase):

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("os.killpg")
    @patch("os.getpgid")
    @patch("os.remove")
    @patch("subprocess.run")
    @patch("nova.browser.manager.BrowserManager.launch_browser")
    def test_restart_browser_uses_pid_file(self, mock_launch_browser, mock_sub_run, mock_os_remove, mock_getpgid, mock_killpg, mock_open_file, mock_exists):
        mock_exists.return_value = True
        mock_getpgid.return_value = 9999
        
        # Mock file read for PID
        from unittest.mock import mock_open
        mock_open_file.side_effect = mock_open(read_data="12345")
        
        BrowserManager.restart_browser()
        
        # Verify it read the PID from file
        mock_open_file.assert_any_call(os.path.join(BrowserManager.AUTOMATED_CHROMIUM_PROFILE, "chromium.pid"), "r")
        # Verify it terminated the process group
        mock_killpg.assert_called_once_with(9999, 15)
        # Verify it cleaned up the PID file
        mock_os_remove.assert_any_call(os.path.join(BrowserManager.AUTOMATED_CHROMIUM_PROFILE, "chromium.pid"))
        # Verify fallback pkill ran matching the profile dir
        mock_sub_run.assert_called_once()
        self.assertIn(f"--user-data-dir={BrowserManager.AUTOMATED_CHROMIUM_PROFILE}", mock_sub_run.call_args[0][0][2])
        # Verify it launched browser at the end
        mock_launch_browser.assert_called_once()

class TestBrowserManagerVerification(NovaBrowserTestCase):

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("os.kill")
    def test_is_process_alive_success(self, mock_kill, mock_open_file, mock_exists):
        mock_exists.return_value = True
        from unittest.mock import mock_open
        mock_open_file.side_effect = mock_open(read_data="12345")
        
        res = BrowserManager.is_process_alive()
        self.assertTrue(res)
        mock_kill.assert_called_once_with(12345, 0)

    @patch("os.path.exists")
    def test_is_process_alive_no_pid_file(self, mock_exists):
        mock_exists.return_value = False
        res = BrowserManager.is_process_alive()
        self.assertFalse(res)

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("os.kill")
    def test_is_process_alive_dead(self, mock_kill, mock_open_file, mock_exists):
        mock_exists.return_value = True
        from unittest.mock import mock_open
        mock_open_file.side_effect = mock_open(read_data="12345")
        mock_kill.side_effect = ProcessLookupError()
        
        res = BrowserManager.is_process_alive()
        self.assertFalse(res)

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("os.kill")
    def test_is_process_alive_permission_denied(self, mock_kill, mock_open_file, mock_exists):
        mock_exists.return_value = True
        from unittest.mock import mock_open
        mock_open_file.side_effect = mock_open(read_data="12345")
        
        import errno
        err = OSError()
        err.errno = errno.EPERM
        mock_kill.side_effect = err
        
        res = BrowserManager.is_process_alive()
        self.assertTrue(res)

    @patch("urllib.request.urlopen")
    def test_is_devtools_http_ready_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        res = BrowserManager.is_devtools_http_ready()
        self.assertTrue(res)

    @patch("urllib.request.urlopen")
    def test_is_devtools_http_ready_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        res = BrowserManager.is_devtools_http_ready()
        self.assertFalse(res)

    @patch("urllib.request.urlopen")
    def test_is_cdp_ready_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = b'{"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        res = BrowserManager.is_cdp_ready()
        self.assertTrue(res)

    @patch("urllib.request.urlopen")
    def test_is_cdp_ready_empty_url(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = b'{"webSocketDebuggerUrl": ""}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        res = BrowserManager.is_cdp_ready()
        self.assertFalse(res)

    @patch("urllib.request.urlopen")
    def test_is_cdp_ready_missing_key(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = b'{}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        res = BrowserManager.is_cdp_ready()
        self.assertFalse(res)

    @patch("time.sleep")
    @patch("nova.browser.manager.BrowserManager.is_cdp_ready")
    @patch("nova.browser.manager.BrowserManager.is_devtools_http_ready")
    @patch("nova.browser.manager.BrowserManager.is_process_alive")
    def test_wait_for_devtools_stages_success(self, mock_alive, mock_http, mock_cdp, mock_sleep):
        mock_alive.return_value = True
        mock_http.return_value = True
        mock_cdp.return_value = True
        
        res = BrowserManager.wait_for_devtools(timeout=5.0)
        self.assertTrue(res)
        
        mock_alive.assert_called()
        mock_http.assert_called()
        mock_cdp.assert_called()

    @patch("time.sleep")
    @patch("nova.browser.manager.BrowserManager.is_cdp_ready")
    @patch("nova.browser.manager.BrowserManager.is_devtools_http_ready")
    @patch("nova.browser.manager.BrowserManager.is_process_alive")
    def test_wait_for_devtools_stage1_fails(self, mock_alive, mock_http, mock_cdp, mock_sleep):
        mock_alive.return_value = False
        
        res = BrowserManager.wait_for_devtools(timeout=1.0)
        self.assertFalse(res)
        mock_alive.assert_called()
        mock_http.assert_not_called()
        mock_cdp.assert_not_called()

if __name__ == "__main__":
    unittest.main()
