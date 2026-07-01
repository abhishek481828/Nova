import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from nova.browser.manager import BrowserManager
from nova.browser.engine import BrowserAutomationEngine, BrowserActionException

class TestBrowserEngine(unittest.TestCase):
    
    def setUp(self):
        BrowserManager.close_connection()
        self.playwright_patcher = patch("nova.browser.manager.sync_playwright")
        self.mock_sync_playwright = self.playwright_patcher.start()
        
        self.mock_playwright = MagicMock()
        self.mock_sync_playwright.return_value.start.return_value = self.mock_playwright
        self.mock_sync_playwright.return_value.__enter__.return_value = self.mock_playwright
        
        # Setup mocks for BrowserManager connections
        self.mock_browser = MagicMock()
        self.mock_context = MagicMock()
        self.mock_page = MagicMock()
        
        self.mock_browser.contexts = [self.mock_context]
        self.mock_context.pages = [self.mock_page]
        self.mock_browser.is_connected.return_value = True
        
        # Configure default element state mocks for all locator-returning page methods
        for m in ("locator", "get_by_test_id", "get_by_text", "get_by_role", "get_by_placeholder", "get_by_label"):
            mock_meth = getattr(self.mock_page, m)
            mock_meth.return_value.count.return_value = 0
            mock_meth.return_value.first.is_disabled.return_value = False
            mock_meth.return_value.first.is_editable.return_value = True
            mock_meth.return_value.is_disabled.return_value = False
            mock_meth.return_value.is_editable.return_value = True
        
        # Patch get_browser and get_persistent_context directly
        self.get_browser_patcher = patch("nova.browser.manager.BrowserManager.get_browser", return_value=self.mock_browser)
        self.mock_get_browser = self.get_browser_patcher.start()
        
        self.context_patcher = patch("nova.browser.manager.BrowserManager.get_persistent_context", return_value=self.mock_context)
        self.mock_get_persistent_context = self.context_patcher.start()
        
        self.engine = BrowserAutomationEngine()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.get_browser_patcher.stop()
        self.context_patcher.stop()
        self.playwright_patcher.stop()
        BrowserManager.close_connection()

    def test_navigate_action(self):
        self.mock_page.url = "https://example.com/navigated"
        self.mock_page.title.return_value = "Example Title"
        
        result = self.engine.execute_action("navigate", {"url": "example.com"})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.goto.assert_called_once_with("https://example.com", timeout=30000.0, wait_until="load")
        self.assertEqual(result["url"], "https://example.com/navigated")
        self.assertEqual(result["title"], "Example Title")

    def test_refresh_action(self):
        self.mock_page.url = "https://example.com"
        result = self.engine.execute_action("refresh", {"timeout": 20000})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.reload.assert_called_once_with(timeout=20000.0, wait_until="load")

    def test_click_action(self):
        result = self.engine.execute_action("click", {"selector": "#submit-btn", "timeout": 15000})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call("#submit-btn")
        self.mock_page.locator.return_value.first.click.assert_called_once_with(
            timeout=5000.0,
            click_count=1,
            button="left",
            modifiers=None,
            force=False,
            no_wait_after=False
        )

    def test_type_action(self):
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        mock_locator.first.is_disabled.return_value = False
        mock_locator.first.is_editable.return_value = True
        self.mock_page.locator.return_value = mock_locator
        
        result = self.engine.execute_action("type", {"selector": "#username", "text": "nova_user", "clear": True})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call("#username")
        mock_locator.first.click.assert_called_once()
        mock_locator.first.fill.assert_called_once_with("", timeout=5000.0)
        mock_locator.first.type.assert_called_once_with("nova_user", delay=0.0, timeout=5000.0)

    def test_hover_action(self):
        result = self.engine.execute_action("hover", {"selector": ".menu-item", "force": True})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call(".menu-item")
        self.mock_page.locator.return_value.first.hover.assert_called_once_with(timeout=5000.0, force=True)

    def test_scroll_window_action(self):
        def mock_evaluate(expr, *args):
            if "innerHeight" in expr:
                return 600
            elif "innerWidth" in expr:
                return 800
            return None
        self.mock_page.evaluate.side_effect = mock_evaluate
        
        result = self.engine.execute_action("scroll", {"direction": "down"})
        self.assertEqual(result["status"], "success")
        self.mock_page.evaluate.assert_any_call("window.scrollBy(0, 600)")
        
        result = self.engine.execute_action("scroll", {"direction": "right", "amount": 150})
        self.assertEqual(result["status"], "success")
        self.mock_page.evaluate.assert_any_call("window.scrollBy(150, 0)")

    def test_scroll_element_action(self):
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        mock_locator.first.is_disabled.return_value = False
        mock_locator.first.is_editable.return_value = True
        self.mock_page.locator.return_value = mock_locator
        
        def mock_eval(expr, *args):
            if "clientHeight" in expr:
                return 300
            return None
        mock_locator.first.evaluate.side_effect = mock_eval
        
        result = self.engine.execute_action("scroll", {"selector": "#div-box", "direction": "down"})
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call("#div-box")
        mock_locator.first.evaluate.assert_any_call("(el, amt) => el.scrollTop += amt", 300)

    def test_drag_and_drop_action(self):
        result = self.engine.execute_action("drag_and_drop", {"source_selector": "#drag", "target_selector": "#drop"})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call("#drag")
        self.mock_page.locator.assert_any_call("#drop")
        source_mock_locator = self.mock_page.locator.return_value
        source_mock_locator.first.drag_to.assert_called_once_with(
            source_mock_locator,
            timeout=5000.0,
            force=False
        )

    def test_upload_file_action(self):
        test_file = __file__
        result = self.engine.execute_action("upload_file", {"selector": "#file-picker", "file_paths": test_file})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call("#file-picker")
        self.mock_page.locator.return_value.first.set_input_files.assert_called_once_with(
            [os.path.abspath(test_file)],
            timeout=5000.0
        )

    def test_download_file_action(self):
        mock_download = MagicMock()
        mock_download.suggested_filename = "report.pdf"
        
        mock_expect = MagicMock()
        mock_expect.value = mock_download
        self.mock_page.expect_download.return_value.__enter__.return_value = mock_expect
        
        result = self.engine.execute_action("download_file", {"click_selector": "#dl-btn", "download_dir": "/tmp/downloads"})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call("#dl-btn")
        self.mock_page.locator.return_value.first.click.assert_called_once()
        mock_download.save_as.assert_called_once_with("/tmp/downloads/report.pdf")
        self.assertEqual(result["suggested_filename"], "report.pdf")
        self.assertEqual(result["path"], "/tmp/downloads/report.pdf")

    def test_press_keys_action(self):
        result = self.engine.execute_action("press_keys", {"selector": "input#query", "key": "Enter"})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call("input#query")
        self.mock_page.locator.return_value.first.focus.assert_called_once_with(timeout=5000.0)
        self.mock_page.keyboard.press.assert_called_once_with("Enter", delay=0.0)

    def test_wait_static_action(self):
        result = self.engine.execute_action("wait", {"seconds": 1.5})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.wait_for_timeout.assert_called_once_with(1500.0)

    def test_wait_selector_action(self):
        result = self.engine.execute_action("wait", {"selector": ".loading-spinner", "state": "hidden", "timeout": 8000})
        
        self.assertEqual(result["status"], "success")
        self.mock_page.locator.assert_any_call(".loading-spinner")
        calls = self.mock_page.locator.return_value.first.wait_for.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["state"], "hidden")
        self.assertAlmostEqual(calls[0][1]["timeout"], 8000.0 / 3.0)

    def test_read_text_action(self):
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        mock_locator.first.is_disabled.return_value = False
        mock_locator.first.is_editable.return_value = True
        self.mock_page.locator.return_value = mock_locator
        mock_locator.first.inner_text.return_value = "Welcome to Nova"
        
        result = self.engine.execute_action("read_text", {"selector": "h1", "mode": "inner_text"})
        
        self.assertEqual(result["status"], "success")
        mock_locator.first.inner_text.assert_called_once()
        self.assertEqual(result["text"], "Welcome to Nova")

    def test_find_elements_action(self):
        mock_locator = MagicMock()
        self.mock_page.locator.return_value = mock_locator
        mock_locator.count.return_value = 2
        
        mock_locator.nth.return_value.evaluate.side_effect = [
            {"tag": "a", "text": "Link 1", "visible": True, "attributes": {"href": "/1"}, "box": {"x": 10, "y": 20, "width": 100, "height": 30}},
            {"tag": "a", "text": "Link 2", "visible": False, "attributes": {"href": "/2"}, "box": {"x": 0, "y": 0, "width": 0, "height": 0}}
        ]
        
        result = self.engine.execute_action("find_elements", {"selector": "a.nav-link"})
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["elements"]), 2)
        self.assertEqual(result["elements"][0]["text"], "Link 1")
        self.assertTrue(result["elements"][0]["visible"])
        self.assertFalse(result["elements"][1]["visible"])

    def test_handle_tabs_list(self):
        mock_page1 = MagicMock()
        mock_page1.title.return_value = "Page 1"
        mock_page1.url = "https://page1.com"
        
        mock_page2 = MagicMock()
        mock_page2.title.return_value = "Page 2"
        mock_page2.url = "https://page2.com"
        
        self.mock_context.pages = [mock_page1, mock_page2]
        self.engine.set_active_page(mock_page1)
        
        result = self.engine.execute_action("handle_tabs", {"operation": "list"})
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["tabs"]), 2)
        self.assertEqual(result["tabs"][0]["title"], "Page 1")
        self.assertTrue(result["tabs"][0]["active"])
        self.assertFalse(result["tabs"][1]["active"])

    def test_handle_tabs_switch(self):
        mock_page1 = MagicMock()
        mock_page1.title.return_value = "Home"
        mock_page1.url = "https://home.com"
        
        mock_page2 = MagicMock()
        mock_page2.title.return_value = "Dashboard"
        mock_page2.url = "https://dashboard.com"
        
        self.mock_context.pages = [mock_page1, mock_page2]
        
        # Switch by index
        result = self.engine.execute_action("handle_tabs", {"operation": "switch", "index": 1})
        self.assertEqual(result["status"], "success")
        mock_page2.bring_to_front.assert_called_once()
        self.assertEqual(self.engine.get_active_page(silent=True), mock_page2)
        
        # Switch by title pattern
        result = self.engine.execute_action("handle_tabs", {"operation": "switch", "title_pattern": "home"})
        self.assertEqual(result["status"], "success")
        mock_page1.bring_to_front.assert_called_once()
        self.assertEqual(self.engine.get_active_page(silent=True), mock_page1)

    def test_handle_windows_list(self):
        mock_ctx1 = MagicMock()
        mock_ctx1.pages = [MagicMock()]
        mock_ctx2 = MagicMock()
        mock_ctx2.pages = [MagicMock(), MagicMock()]
        
        self.mock_browser.contexts = [mock_ctx1, mock_ctx2]
        self.engine.set_active_context(mock_ctx1)
        
        result = self.engine.execute_action("handle_windows", {"operation": "list"})
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["windows"]), 2)
        self.assertEqual(result["windows"][0]["pages_count"], 1)
        self.assertTrue(result["windows"][0]["active"])
        self.assertEqual(result["windows"][1]["pages_count"], 2)
        self.assertFalse(result["windows"][1]["active"])

    def test_handle_windows_switch(self):
        mock_ctx1 = MagicMock()
        mock_ctx1.pages = [MagicMock()]
        mock_ctx2 = MagicMock()
        mock_page_in_ctx2 = MagicMock()
        mock_ctx2.pages = [mock_page_in_ctx2]
        
        self.mock_browser.contexts = [mock_ctx1, mock_ctx2]
        
        result = self.engine.execute_action("handle_windows", {"operation": "switch", "index": 1})
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.engine.get_active_context(), mock_ctx2)
        mock_page_in_ctx2.bring_to_front.assert_called_once()

    def test_is_raw_selector(self):
        detector = self.engine._detector
        self.assertTrue(detector.is_raw_selector("#login"))
        self.assertTrue(detector.is_raw_selector(".btn-primary"))
        self.assertTrue(detector.is_raw_selector("//button"))
        self.assertTrue(detector.is_raw_selector("input[name='email']"))
        self.assertFalse(detector.is_raw_selector("Username Input"))
        self.assertFalse(detector.is_raw_selector("login button"))

    def test_detect_element_raw_selector(self):
        # Should directly pass raw selectors to page.locator
        detector = self.engine._detector
        locator = detector.detect_element(self.mock_page, "#submit-btn", "click")
        self.mock_page.locator.assert_any_call("#submit-btn")

    def test_detect_element_semantic(self):
        # Mock evaluate to return candidates
        detector = self.engine._detector
        self.mock_page.evaluate.return_value = [
            {"xpath": "/html/body/div/button", "score": 180, "tag": "button"}
        ]
        
        locator = detector.detect_element(self.mock_page, "Submit Button", "click")
        
        self.mock_page.evaluate.assert_called_once()
        self.mock_page.locator.assert_any_call("xpath=/html/body/div/button")

    def test_find_elements_semantic(self):
        detector = self.engine._detector
        # Set return value for detect_all_elements
        self.mock_page.evaluate.return_value = [
            {"xpath": "/html/body/div/a[1]", "tag": "a", "text": "Link 1", "visible": True, "attributes": {"href": "/1"}, "box": {"x": 10, "y": 20, "width": 100, "height": 30}},
            {"xpath": "/html/body/div/a[2]", "tag": "a", "text": "Link 2", "visible": True, "attributes": {"href": "/2"}, "box": {"x": 10, "y": 50, "width": 100, "height": 30}}
        ]
        
        result = self.engine.execute_action("find_elements", {"selector": "Navigation Link"})
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["elements"][0]["text"], "Link 1")
        self.assertEqual(result["elements"][1]["xpath"], "/html/body/div/a[2]")

    def test_interact_with_retry_success_first_time(self):
        mock_action = MagicMock(return_value="Success")
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        mock_locator.first.is_disabled.return_value = False
        self.mock_page.locator.return_value = mock_locator
        
        result = self.engine.interact_with_retry("#target", "click", mock_action)
        
        self.assertEqual(result, "Success")
        mock_action.assert_called_once_with(mock_locator.first)
        mock_locator.first.scroll_into_view_if_needed.assert_not_called()

    def test_interact_with_retry_success_after_retry(self):
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        mock_locator.first.is_disabled.return_value = False
        self.mock_page.locator.return_value = mock_locator
        
        # Action fails first time, succeeds second time
        mock_action = MagicMock(side_effect=[Exception("Click intercepted"), "Success"])
        
        result = self.engine.interact_with_retry("#target", "click", mock_action, max_retries=2)
        
        self.assertEqual(result, "Success")
        self.assertEqual(mock_action.call_count, 2)

    def test_interact_with_retry_exhaust_retries(self):
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        mock_locator.first.is_disabled.return_value = False
        self.mock_page.locator.return_value = mock_locator
        
        # Always fails
        mock_action = MagicMock(side_effect=Exception("Failed interaction"))
        
        with self.assertRaises(BrowserActionException) as context:
            self.engine.interact_with_retry("#target", "click", mock_action, max_retries=3)
            
        self.assertIn("failed after 3 attempts", str(context.exception))
        self.assertEqual(mock_action.call_count, 3)

    def test_attach_page_listeners(self):
        page = MagicMock()
        self.engine._attach_page_listeners(page)
        
        self.assertTrue(page._diagnostics_attached)
        self.assertEqual(page._console_logs, [])
        self.assertEqual(page._network_errors, [])
        page.on.assert_any_call("console", unittest.mock.ANY)
        page.on.assert_any_call("requestfailed", unittest.mock.ANY)

    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch("os.makedirs")
    def test_capture_diagnostics(self, mock_makedirs, mock_open_file):
        self.mock_page.url = "https://example.com/fail"
        self.mock_page.content.return_value = "<html>Fail</html>"
        self.mock_page._console_logs = ["[error] Console Error"]
        self.mock_page._network_errors = ["Failed request: GET /api - 500"]
        
        diag = self.engine.capture_diagnostics(Exception("Test Error"))
        
        self.assertIn("screenshot", diag)
        self.assertIn("html", diag)
        self.assertIn("report", diag)
        self.mock_page.screenshot.assert_called_once()
        self.mock_page.content.assert_called_once()
        mock_open_file.assert_called()

    @patch("nova.logger.logger.info")
    @patch("nova.logger.logger.error")
    def test_step_logging_success(self, mock_log_err, mock_log_info):
        result = self.engine.execute_action("navigate", {"url": "example.com"})
        
        self.assertEqual(result["status"], "success")
        mock_log_info.assert_any_call("Nova Automation Step Start - Operation: navigate, Parameters: {'url': 'example.com'}")
        self.assertTrue(any("Nova Automation Step Success" in str(call) for call in mock_log_info.call_args_list))

    @patch("nova.logger.logger.info")
    @patch("nova.logger.logger.error")
    @patch("nova.browser.engine.BrowserAutomationEngine.capture_diagnostics")
    def test_step_logging_failure(self, mock_capture, mock_log_err, mock_log_info):
        mock_action = MagicMock()
        mock_action.execute.side_effect = Exception("Action failure")
        self.engine._actions["click"] = mock_action
        
        result = self.engine.execute_action("click", {"selector": "#btn"})
        
        self.assertEqual(result["status"], "error")
        mock_log_info.assert_any_call("Nova Automation Step Start - Operation: click, Parameters: {'selector': '#btn'}")
        self.assertTrue(any("Nova Automation Step Exception" in str(call) for call in mock_log_err.call_args_list))
        mock_capture.assert_called_once()

    @patch("nova.browser.engine.BrowserAutomationEngine.execute_action")
    def test_fill_form_action(self, mock_exec):
        mock_exec.return_value = {"status": "success"}
        from nova.browser.engine import FillFormAction
        action = FillFormAction()
        result = action.execute(self.engine, {"fields": {"Email": "user@ex.com", "Password": "pwd"}})
        self.assertEqual(result["status"], "success")
        mock_exec.assert_any_call("type", {"selector": "Email", "text": "user@ex.com", "timeout": 15000})
        mock_exec.assert_any_call("type", {"selector": "Password", "text": "pwd", "timeout": 15000})

    @patch("nova.browser.engine.BrowserAutomationEngine.detect_login", return_value=True)
    def test_detect_login_action(self, mock_detect):
        result = self.engine.execute_action("detect_login", {})
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["logged_in"])

    @patch("nova.browser.manager.BrowserManager.close_connection")
    @patch("nova.browser.engine.BrowserAutomationEngine.get_browser_instance")
    @patch("nova.browser.engine.BrowserAutomationEngine.get_active_context")
    @patch("nova.browser.engine.BrowserAutomationEngine.get_active_page")
    def test_recover_browser(self, mock_page, mock_context, mock_browser, mock_close):
        self.engine._active_context = MagicMock()
        self.engine._active_page = MagicMock()
        
        self.engine.recover_browser()
        
        mock_close.assert_called_once()
        self.assertIsNone(self.engine._active_context)
        self.assertIsNone(self.engine._active_page)
        mock_browser.assert_called_once()
        mock_context.assert_called_once()
        mock_page.assert_called_once()

    @patch("nova.browser.engine.BrowserAutomationEngine.recover_browser")
    def test_browser_disconnect_recovery_flow(self, mock_recover):
        mock_action = MagicMock()
        mock_action.execute.side_effect = Exception("Target page, context or browser has been closed")
        self.engine._actions["click"] = mock_action
        
        result = self.engine.execute_action("click", {"selector": "#btn"})
        
        self.assertEqual(result["status"], "error")
        mock_recover.assert_called_once()

    def test_popup_listener_registration(self):
        mock_page = MagicMock()
        self.engine._attach_page_listeners(mock_page)
        mock_page.on.assert_any_call("popup", unittest.mock.ANY)

if __name__ == "__main__":
    unittest.main()
