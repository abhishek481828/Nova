from nova.adapters.base_adapter import BaseWebsiteAdapter
from nova.browser.engine import BrowserActionException

class GmailAdapter(BaseWebsiteAdapter):
    """Website Adapter for Gmail workflows."""
    
    def search_mail(self, query: str) -> None:
        """Searches Gmail inbox for the specified query."""
        try:
            page = self.engine.get_active_page(silent=True)
            if "mail.google.com" not in page.url:
                self._execute("navigate", {"url": "https://mail.google.com"})
                
            self._execute("type", {"selector": "input[placeholder='Search mail']", "text": query})
            self._execute("press_keys", {"selector": "input[placeholder='Search mail']", "key": "Enter"})
            self._execute("wait", {"seconds": 2.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"Gmail search_mail workflow failed: {e}")

    def compose_email(self, to_address: str, subject: str, body: str) -> None:
        """Composes and sends an email to the target address."""
        try:
            page = self.engine.get_active_page(silent=True)
            if "mail.google.com" not in page.url:
                self._execute("navigate", {"url": "https://mail.google.com"})
                
            self._execute("click", {"selector": "div[role='button']:has-text('Compose')"})
            self._execute("wait", {"seconds": 1.5})
            
            self._execute("type", {"selector": "input[peoplekit-id]", "text": to_address})
            self._execute("press_keys", {"selector": "input[peoplekit-id]", "key": "Enter"})
            
            self._execute("type", {"selector": "input[name='subjectbox']", "text": subject})
            self._execute("type", {"selector": "div[role='textbox'][aria-label*='Message Body']", "text": body})
            
            self._execute("click", {"selector": "div[role='button'][aria-label*='Send']"})
            self._execute("wait", {"seconds": 1.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"Gmail compose_email workflow failed: {e}")

    def open_latest_mail(self) -> None:
        """Opens the latest email from the inbox list."""
        try:
            page = self.engine.get_active_page(silent=True)
            if "mail.google.com" not in page.url:
                self._execute("navigate", {"url": "https://mail.google.com"})
                
            self._execute("click", {"selector": "div[role='main'] tr[role='row']"})
            self._execute("wait", {"seconds": 2.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"Gmail open_latest_mail workflow failed: {e}")

    def reply_to_latest_mail(self, body: str) -> None:
        """Replies to the currently open email thread."""
        try:
            self._execute("click", {"selector": "span[role='link']:has-text('Reply')"})
            self._execute("wait", {"seconds": 1.5})
            
            self._execute("type", {"selector": "div[role='textbox'][aria-label*='Message Body']", "text": body})
            self._execute("click", {"selector": "div[role='button'][aria-label*='Send']"})
            self._execute("wait", {"seconds": 1.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"Gmail reply_to_latest_mail workflow failed: {e}")
