import time
import re
import logging
from typing import Any, Dict, List, Optional, Callable
try:
    from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError
    TimeoutError = PlaywrightTimeoutError
except ImportError:
    Page = Locator = None  # type: ignore[assignment,misc]


logger = logging.getLogger("nova")

class BrowserInteractionHelper:
    """
    Resilient Browser Interaction Helper for modern dynamic web applications.
    Replaces raw/fragile selectors with prioritized semantic locators, close overlays,
    checks element stability, and performs retries with exponential backoff.
    """

    @classmethod
    def is_raw_selector(cls, query: str) -> bool:
        """Determines if a string is a CSS or XPath selector."""
        s = query.strip()
        if s.startswith(("/", "xpath=", "./", "(")):
            return True
        if any(c in s for c in ("#", ".", "[", "]", ">", ":", "=")):
            return True
        return False

    @classmethod
    def get_alternative_locators(cls, page: Page, query: str, action_type: str) -> List[Locator]:
        """
        Generates a list of alternative semantic locators based on priority.
        """
        locators: List[Locator] = []

        if cls.is_raw_selector(query):
            # Direct locator fallback
            locators.append(page.locator(query))
            
            # Try to extract semantic clues from CSS/XPath (e.g. text or id)
            match_id = re.search(r'#([a-zA-Z0-9_\-]+)', query)
            if match_id:
                locators.append(page.get_by_test_id(match_id.group(1)))
                
            match_text = re.search(r':has-text\([\'"](.+?)[\'"]\)', query)
            if match_text:
                locators.append(page.get_by_text(match_text.group(1), exact=False))
        else:
            # Semantic query text
            if action_type == "type":
                locators.extend([
                    page.get_by_placeholder(query, exact=False),
                    page.get_by_label(query, exact=False),
                    page.get_by_role("textbox", name=query, exact=False),
                    page.get_by_role("combobox", name=query, exact=False),
                    page.get_by_role("searchbox", name=query, exact=False),
                    page.locator(f"input[name='{query}']"),
                    page.locator(f"textarea[name='{query}']"),
                    page.get_by_text(query, exact=False),
                    page.locator(query)
                ])
            else: # click/hover actions
                locators.extend([
                    page.get_by_role("button", name=query, exact=False),
                    page.get_by_role("link", name=query, exact=False),
                    page.get_by_text(query, exact=False),
                    page.get_by_label(query, exact=False),
                    page.locator(f"button:has-text('{query}')"),
                    page.locator(f"a:has-text('{query}')"),
                    page.get_by_placeholder(query, exact=False),
                    page.locator(query)
                ])

        return locators

    @classmethod
    def select_active_element(cls, locators: List[Locator]) -> Optional[Locator]:
        """
        Iterates over alternative locators and candidates to find the first visible & enabled one.
        """
        for index, loc in enumerate(locators):
            try:
                count = loc.count()
                for i in range(count):
                    candidate = loc.nth(i)
                    if candidate.is_visible() and candidate.is_enabled():
                        logger.debug(f"Selected active locator at index {index} (candidate {i})")
                        return candidate
            except Exception:
                continue
        return None

    @classmethod
    def wait_for_stability(cls, locator: Locator, timeout_ms: int = 1500) -> bool:
        """
        Waits for the element's position/dimensions to settle (e.g. after animations).
        """
        start_time = time.time()
        try:
            box = locator.bounding_box()
            if not box:
                return False
            while time.time() - start_time < (timeout_ms / 1000.0):
                time.sleep(0.1)
                new_box = locator.bounding_box()
                if not new_box:
                    return False
                if (new_box["x"] == box["x"] and 
                    new_box["y"] == box["y"] and 
                    new_box["width"] == box["width"] and 
                    new_box["height"] == box["height"]):
                    return True
                box = new_box
        except Exception:
            pass
        return False

    @classmethod
    def is_element_covered(cls, page: Page, locator: Locator) -> bool:
        """
        Uses page javascript evaluation to verify if element is obscured by overlays.
        """
        try:
            return locator.evaluate("""
                (target) => {
                    const rect = target.getBoundingClientRect();
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const topEl = document.elementFromPoint(x, y);
                    if (!topEl) return false;
                    
                    let curr = topEl;
                    while (curr) {
                        if (curr === target) return false;
                        curr = curr.parentNode;
                    }
                    return true;
                }
            """)
        except Exception:
            return False

    @classmethod
    def handle_overlays(cls, page: Page) -> bool:
        """
        Scans for visible modal dialogs, cookie popups, or onboarding overlays and dismisses them.
        Returns True if an overlay was closed.
        """
        overlay_selectors = [
            "role=dialog",
            "role=alertdialog",
            ".modal",
            ".overlay",
            ".popup",
            "[class*='modal-backdrop']",
            "[class*='Overlay']",
            "[id*='overlay']",
            "[id*='modal']",
            "[id*='popup']",
            "[class*='cookie']",
            "[class*='banner']"
        ]
        
        for sel in overlay_selectors:
            try:
                loc = page.locator(sel)
                for i in range(loc.count()):
                    el = loc.nth(i)
                    if el.is_visible():
                        logger.info(f"Blocking overlay detected: '{sel}'")
                        
                        # Try to find common close buttons inside the overlay
                        close_triggers = [
                            el.get_by_role("button", name="Close", exact=False),
                            el.get_by_role("button", name="Dismiss", exact=False),
                            el.get_by_role("button", name="Accept", exact=False),
                            el.get_by_role("button", name="Agree", exact=False),
                            el.locator("[class*='close']"),
                            el.locator("text='×'")
                        ]
                        
                        for trigger in close_triggers:
                            if trigger.count() > 0 and trigger.first.is_visible() and trigger.first.is_enabled():
                                logger.info("Found dismiss trigger. Clicking to close overlay...")
                                trigger.first.click(timeout=3000)
                                page.wait_for_timeout(500)
                                return True
            except Exception as e:
                logger.debug(f"Overlay dismissal attempt failed: {e}")
                
        return False

    @classmethod
    def execute_interaction(
        cls,
        page: Page,
        query: str,
        action_type: str,
        action_fn: Callable[[Locator], Any],
        max_retries: int = 3,
        initial_delay: float = 0.5
    ) -> Any:
        """
        Core resilience loop: resolves locators, dismisses overlays, wait for stability, and retries on errors.
        """
        logger.info(f"Resilient interaction start: '{query}' -> type: {action_type}")
        
        # DOM load sync checks
        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass

        alternative_locators = cls.get_alternative_locators(page, query, action_type)
        delay = initial_delay
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                # 1. Look for overlays blocking screen
                overlay_closed = cls.handle_overlays(page)
                if overlay_closed:
                    page.wait_for_timeout(500)

                # 2. Select the first actionable locator element
                active_element = cls.select_active_element(alternative_locators)
                if active_element is None:
                    # Fallback directly to native selector search
                    active_element = page.locator(query).first
                    
                # 3. Perform actionability checks
                if not active_element.is_visible():
                    raise TimeoutError(f"Element '{query}' is not visible.")
                if not active_element.is_enabled():
                    raise ValueError(f"Element '{query}' is disabled.")
                
                # 4. Wait for stability (animations)
                cls.wait_for_stability(active_element)

                # 5. Check if obscured
                if cls.is_element_covered(page, active_element):
                    logger.warning(f"Element '{query}' appears obscured. Attempting to dismiss overlays again...")
                    cls.handle_overlays(page)

                # 6. Execute action
                result = action_fn(active_element)
                logger.info(f"Resilient interaction success: '{query}' (Attempt {attempt})")
                return result

            except Exception as e:
                last_exception = e
                err_msg = str(e).lower()
                logger.warning(
                    f"Resilient interaction attempt {attempt} failed for '{query}'. "
                    f"Error: {e}. Retrying in {delay}s..."
                )
                
                # Reconnect if browser lost
                if any(kw in err_msg for kw in ("closed", "disconnected", "target closed", "connection lost", "crashed")):
                    logger.error("Browser crashed or disconnected. Terminating retry loop.")
                    raise e
                    
                time.sleep(delay)
                delay *= 2

        # Log detailed diagnostics before reporting failure
        raise TimeoutError(
            f"Resilient browser interaction on '{query}' failed after {max_retries} attempts.\n"
            f"Action type: {action_type}\n"
            f"Attempted locators: {[str(loc) for loc in alternative_locators]}\n"
            f"Last exception caught: {last_exception}"
        )
