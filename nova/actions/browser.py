import webbrowser
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.utils import print_info

class BrowserAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "browser_action"

    def execute(self, params: Dict[str, Any]) -> str:
        url = params.get("url", "").strip()
        if not url:
            return "Error: No URL provided for browser action."

        # Add https scheme if not present
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        print_info(f"Opening URL in default browser: {url}")
        
        success = webbrowser.open(url)
        
        if success:
            return f"Successfully opened default browser to: {url}"
        else:
            return f"Webbrowser module failed to launch url: {url}"
