try:
    from nova.browser.manager import BrowserManager, find_active_page
    from nova.browser.engine import BrowserAutomationEngine, BrowserActionException
    from nova.browser.helper import run_automation
    from nova.browser.interaction import BrowserInteractionHelper
    from nova.browser.actions import BrowserAction, ChromiumAction
except ImportError:
    # Optional dependencies (playwright) not installed — browser submodules
    # are available but must be imported individually after installing deps.
    pass
