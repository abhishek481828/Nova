from nova.adapters.base_adapter import BaseWebsiteAdapter

class LinkedInAdapter(BaseWebsiteAdapter):
    """Website Adapter for LinkedIn workflows."""
    
    def send_message(self, recipient_name: str, message: str) -> None:
        """Searches for a recipient and sends them a message on LinkedIn Messaging."""
        self._execute("navigate", {"url": "https://www.linkedin.com/messaging/"})
        self._execute("type", {"selector": "input[placeholder='Search messages']", "text": recipient_name})
        self._execute("press_keys", {"selector": "input[placeholder='Search messages']", "key": "Enter"})
        self._execute("wait", {"seconds": 1.5})
        
        self._execute("click", {"selector": f"h3:has-text('{recipient_name}')"})
        self._execute("type", {"selector": "div[role='textbox'][aria-label*='Write a message']", "text": message})
        self._execute("click", {"selector": "button[type='submit']:has-text('Send')"})

    def connect_with_user(self, profile_url: str, message: str = "") -> None:
        """Navigates to a user's LinkedIn profile and sends a connection request."""
        self._execute("navigate", {"url": profile_url})
        
        try:
            self._execute("click", {"selector": "button:has-text('Connect')"})
        except Exception:
            self._execute("click", {"selector": "button:has-text('More')"})
            self._execute("click", {"selector": "div[role='button']:has-text('Connect')"})
            
        self._execute("wait", {"seconds": 1.0})
        
        if message:
            self._execute("click", {"selector": "button[aria-label='Add a note']"})
            self._execute("type", {"selector": "textarea[name='message']", "text": message})
            self._execute("click", {"selector": "button[aria-label='Send now']"})
        else:
            self._execute("click", {"selector": "button[aria-label='Send without a note']"})
