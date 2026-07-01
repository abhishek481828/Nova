import unittest
from unittest.mock import MagicMock, patch
import time
from playwright.sync_api import sync_playwright

from nova.browser_interaction_helper import BrowserInteractionHelper
from nova.browser_helper import ChatGPTHandler, GmailHandler, GitHubHandler, GoogleSearchHandler

class TestBrowserResilience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop:
                loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(None)
            
        from nova.browser_manager import BrowserManager
        try:
            cls.browser = BrowserManager.get_browser()
            cls.cdp = True
        except Exception:
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(
                headless=True,
                executable_path="/run/current-system/sw/bin/chromium"
            )
            cls.cdp = False
        cls.context = cls.browser.new_context()

    @classmethod
    def tearDownClass(cls):
        cls.context.close()
        if not getattr(cls, "cdp", False):
            cls.browser.close()
            if hasattr(cls, "playwright"):
                cls.playwright.stop()

    def setUp(self):
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()

    def test_multiple_submit_buttons(self):
        # HTML with multiple submit buttons, one hidden, one disabled, one active
        self.page.set_content("""
            <html>
                <body>
                    <button type="submit" style="display:none;">Submit</button>
                    <button type="submit" disabled>Submit</button>
                    <button type="submit" id="active-btn" onclick="window.clicked=true">Submit</button>
                </body>
            </html>
        """)
        
        # Click "Submit" semantic query
        BrowserInteractionHelper.execute_interaction(
            page=self.page,
            query="Submit",
            action_type="click",
            action_fn=lambda loc: loc.click(),
            max_retries=2
        )
        
        clicked = self.page.evaluate("window.clicked")
        self.assertTrue(clicked)

    def test_overlay_dismissal(self):
        # HTML with a blocking overlay banner
        self.page.set_content("""
            <html>
                <body>
                    <div id="cookie-overlay" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:999;">
                        <p>We use cookies</p>
                        <button id="agree-btn" onclick="document.getElementById('cookie-overlay').style.display='none'">Agree</button>
                    </div>
                    <button id="target-btn" onclick="window.targetClicked=true">Target Button</button>
                </body>
            </html>
        """)
        
        # When attempting to click target, overlay is detected and closed via "Agree"
        BrowserInteractionHelper.execute_interaction(
            page=self.page,
            query="Target Button",
            action_type="click",
            action_fn=lambda loc: loc.click(),
            max_retries=2
        )
        
        target_clicked = self.page.evaluate("window.targetClicked")
        overlay_visible = self.page.evaluate("document.getElementById('cookie-overlay').style.display !== 'none'")
        
        self.assertTrue(target_clicked)
        self.assertFalse(overlay_visible)

    def test_disabled_button_raises(self):
        self.page.set_content("""
            <html>
                <body>
                    <button id="target" disabled>Click Me</button>
                </body>
            </html>
        """)
        
        with self.assertRaises(Exception):
            BrowserInteractionHelper.execute_interaction(
                page=self.page,
                query="Click Me",
                action_type="click",
                action_fn=lambda loc: loc.click(),
                max_retries=1
            )

    def test_hidden_element_raises(self):
        self.page.set_content("""
            <html>
                <body>
                    <button id="target" style="display:none;">Click Me</button>
                </body>
            </html>
        """)
        
        with self.assertRaises(Exception):
            BrowserInteractionHelper.execute_interaction(
                page=self.page,
                query="Click Me",
                action_type="click",
                action_fn=lambda loc: loc.click(),
                max_retries=1
            )

    def test_dynamic_element_loading(self):
        # Button appears after a short delay
        self.page.set_content("""
            <html>
                <body>
                    <script>
                        setTimeout(() => {
                            const btn = document.createElement("button");
                            btn.id = "dynamic";
                            btn.innerText = "Loaded Button";
                            btn.onclick = () => { window.dynamicClicked = true; };
                            document.body.appendChild(btn);
                        }, 500);
                    </script>
                </body>
            </html>
        """)
        
        BrowserInteractionHelper.execute_interaction(
            page=self.page,
            query="Loaded Button",
            action_type="click",
            action_fn=lambda loc: loc.click(),
            max_retries=3,
            initial_delay=0.3
        )
        
        self.assertTrue(self.page.evaluate("window.dynamicClicked"))

    @patch("nova.browser_helper.smart_fill")
    def test_chatgpt_handler_integration(self, mock_smart_fill):
        # Set up ChatGPT mockup page
        self.page.set_content("""
            <html>
                <body>
                    <textarea id="prompt-textarea"></textarea>
                    <button aria-label="Send prompt" onclick="window.sent=true">Send</button>
                </body>
            </html>
        """)
        
        handler = ChatGPTHandler()
        params = {"operation": "fill_form", "value": "write a python script"}
        res = handler.handle(self.page, "tell chatgpt to write a python script", params)
        
        self.assertEqual(res["status"], "success")
        mock_smart_fill.assert_called_once_with(self.page, "textarea#prompt-textarea", "a python script")
        self.assertTrue(self.page.evaluate("window.sent"))

    @patch("nova.browser_helper.smart_fill")
    def test_gmail_handler_integration(self, mock_smart_fill):
        self.page.set_content("""
            <html>
                <body>
                    <input name="q" />
                </body>
            </html>
        """)
        
        handler = GmailHandler()
        params = {"operation": "fill_form", "value": "receipts"}
        res = handler.handle(self.page, "search gmail for receipts", params)
        
        self.assertEqual(res["status"], "success")
        mock_smart_fill.assert_called_once_with(self.page, "input[name='q']", "receipts")

    @patch("nova.browser_helper.smart_fill")
    def test_github_handler_integration(self, mock_smart_fill):
        self.page.set_content("""
            <html>
                <body>
                    <input id="query-builder-test" />
                </body>
            </html>
        """)
        
        handler = GitHubHandler()
        params = {"operation": "fill_form", "value": "Nova"}
        res = handler.handle(self.page, "search github for Nova", params)
        
        self.assertEqual(res["status"], "success")
        mock_smart_fill.assert_called_once_with(self.page, "input#query-builder-test", "Nova")

    @patch("nova.browser_helper.smart_fill")
    def test_google_search_handler_integration(self, mock_smart_fill):
        self.page.set_content("""
            <html>
                <body>
                    <textarea name="q"></textarea>
                </body>
            </html>
        """)
        
        handler = GoogleSearchHandler()
        params = {"operation": "fill_form", "value": "weather today"}
        res = handler.handle(self.page, "google weather today", params)
        
        self.assertEqual(res["status"], "success")
        mock_smart_fill.assert_called_once_with(self.page, "textarea[name='q']", "weather today")

if __name__ == "__main__":
    unittest.main()
