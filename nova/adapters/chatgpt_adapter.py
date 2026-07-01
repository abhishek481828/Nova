import time
from nova.adapters.base_adapter import BaseWebsiteAdapter
from nova.browser.engine import BrowserActionException

class ChatGPTAdapter(BaseWebsiteAdapter):
    """Website Adapter for ChatGPT workflows."""
    
    def is_logged_in(self) -> bool:
        """Detects if ChatGPT is in a logged-in state or displays login prompts."""
        page = self.engine.get_active_page(silent=True)
        try:
            for query in ("Log in", "Sign up"):
                loc = self.engine.resolve_locator(page, query, "click")
                if loc.first.is_visible(timeout=1000):
                    return False
        except Exception:
            pass
        return True

    def handle_cookie_dialog(self) -> None:
        """Detects and accepts cookie consent dialogs if present."""
        page = self.engine.get_active_page(silent=True)
        cookie_accept_queries = ("Accept all", "Allow all cookies", "Accept all cookies", "Accept cookies", "Accept")
        for query in cookie_accept_queries:
            try:
                loc = self.engine.resolve_locator(page, query, "click")
                if loc.first.is_visible(timeout=1000):
                    loc.first.click(timeout=2000)
                    time.sleep(0.5)
                    return
            except Exception:
                pass

    def handle_onboarding_dialogs(self) -> None:
        """Dismisses any onboarding or welcome modals by clicking 'Next', 'Done', 'Got it', etc."""
        page = self.engine.get_active_page(silent=True)
        dismiss_queries = ("Next", "Done", "Got it", "Dismiss", "Close", "Okay, let's go", "Okay")
        
        for _ in range(5):
            clicked_any = False
            for query in dismiss_queries:
                try:
                    loc = self.engine.resolve_locator(page, query, "click")
                    if loc.first.is_visible(timeout=1000):
                        loc.first.click(timeout=2000)
                        clicked_any = True
                        time.sleep(0.5)
                        break
                except Exception:
                    pass
            if not clicked_any:
                break

    def ask_question(self, prompt: str) -> str:
        """Sends a question to ChatGPT and returns the generated response."""
        try:
            # 1. Load Page & Wait
            self._execute("navigate", {"url": "https://chatgpt.com"})
            self._execute("wait", {"seconds": 2.0})
            
            # 2. Handle Cookies & Onboarding Dialogs
            self.handle_cookie_dialog()
            self.handle_onboarding_dialogs()
            
            # 3. Detect Login
            if not self.is_logged_in():
                raise BrowserActionException("User is not logged in to ChatGPT. Authentication is required.")
                
            # 4. Detect, Verify Prompt Input Box (Visible & Editable)
            page = self.engine.get_active_page(silent=True)
            prompt_locator = self.engine.resolve_locator(page, "prompt textarea", "type")
            
            if not prompt_locator.first.is_visible(timeout=3000):
                raise BrowserActionException("Prompt textarea is not visible.")
            if not prompt_locator.first.is_editable(timeout=3000):
                raise BrowserActionException("Prompt textarea is not editable.")
                
            # 5. Type and Submit Prompt
            self._execute("type", {"selector": "prompt textarea", "text": prompt})
            
            send_btn = None
            try:
                loc = self.engine.resolve_locator(page, "Send message", "click")
                if loc.first.is_visible(timeout=1000):
                    send_btn = loc
            except Exception:
                pass
                
            if send_btn:
                self._execute("click", {"selector": "Send message"})
            else:
                self._execute("press_keys", {"selector": "prompt textarea", "key": "Enter"})
                
            # 6. Wait for Response Generation
            try:
                stop_loc = self.engine.resolve_locator(page, "Stop generating", "click")
                stop_loc.first.wait_for(state="visible", timeout=3000)
            except Exception:
                pass
                
            try:
                stop_loc = self.engine.resolve_locator(page, "Stop generating", "click")
                stop_loc.first.wait_for(state="hidden", timeout=30000)
            except Exception:
                pass
                
            self._execute("wait", {"seconds": 1.0})
            
            # 7. Extract & Return Response
            res = self._execute("read_text", {"selector": ".markdown", "mode": "inner_text"})
            return res.get("text", "")
            
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"ChatGPT ask_question workflow failed: {e}")
