from nova.browser_engine import BrowserAutomationEngine, BrowserActionException

class BaseWebsiteAdapter:
    """Base class for all website adapters, providing unified access to BrowserAutomationEngine."""
    
    def __init__(self, engine: BrowserAutomationEngine):
        self.engine = engine

    def _execute(self, action_type: str, params: dict) -> dict:
        """Helper to execute an action on the engine and raise BrowserActionException on error."""
        res = self.engine.execute_action(action_type, params)
        if res.get("status") == "error":
            raise BrowserActionException(
                f"Website Adapter step failed - Operation: '{action_type}' with params {params}. "
                f"Error: {res.get('message')}"
            )
        return res
