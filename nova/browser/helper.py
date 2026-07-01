import sys
import json
import re
import os
from pathlib import Path

# Add project root directory to path to allow importing nova
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from playwright.sync_api import sync_playwright, Page, BrowserContext
except ImportError:
    sync_playwright = Page = BrowserContext = None  # type: ignore[assignment,misc]


from nova.browser.manager import BrowserManager

YOUTUBE_DOMAIN = "youtube.com"
YOUTUBE_SEARCH_BOX_SELECTOR = 'input[name="search_query"]'
YOUTUBE_VIDEO_RESULT_SELECTOR = "ytd-video-renderer a#video-title"

YOUTUBE_WATCH_URL_PATTERN = "**/watch*"


# ---------------------------------------------------------------------------
# Low-level safety helpers
# ---------------------------------------------------------------------------

def _safe_eval(page: Page, expression: str, default: bool = False) -> bool:
    """Evaluate a JS expression on a page, swallowing errors (e.g. closed page)."""
    try:
        return bool(page.evaluate(expression))
    except Exception:
        return default


def focus_page(page: Page) -> None:
    """Bring a page to the foreground. Never raises."""
    BrowserManager.focus_browser(page)


def url_belongs_to_domain(url: str, domain: str) -> bool:
    """True if `domain` (e.g. 'youtube.com') appears in the page URL's host."""
    return domain.lower() in (url or "").lower()


def wait_for_page_ready(page: Page, timeout: int = 15000) -> None:
    """
    Wait for the page to settle without relying on fixed sleeps.
    networkidle is best-effort: some sites keep background connections open
    indefinitely, so a timeout here is not treated as fatal — callers should
    wait on specific selectors/URLs for anything that truly must be ready.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Generic page / tab selection
# ---------------------------------------------------------------------------
# All "which tab do I act on" logic funnels through one priority order:
#   1. Visible page
#   2. Focused page
#   3. Existing page matching the requested domain (if any)
#   4. First open page
# This is used both for generic active-page lookup and for domain-aware
# lookup (find_page_by_domain), so there is exactly one place that encodes
# "never randomly choose a page".

def _visible_page(pages):
    for page in pages:
        if _safe_eval(page, "document.visibilityState === 'visible'"):
            return page
    return None


def _focused_page(pages):
    for page in pages:
        if _safe_eval(page, "document.hasFocus()"):
            return page
    return None


def find_active_page(context: BrowserContext) -> Page:
    """
    Find the page the user is most likely looking at right now.
    Priority: visible -> focused -> first open page -> new blank page.
    """
    pages = context.pages
    safe_pages = [p for p in pages if not (p.url or "").startswith("chrome-extension://")]
    return (
        _visible_page(safe_pages)
        or _focused_page(safe_pages)
        or (safe_pages[0] if safe_pages else None)
        or context.new_page()
    )


def find_page_by_domain(context: BrowserContext, domain: str):
    """
    Find the best existing tab for a given domain (e.g. "youtube.com",
    "github.com"), if one exists.

    Priority among tabs matching the domain:
        1. Visible tab
        2. Focused tab
        3. First matching tab
    Returns None if no tab for that domain is open.
    """
    matching = [p for p in context.pages if url_belongs_to_domain(p.url, domain)]
    if not matching:
        return None
    return _visible_page(matching) or _focused_page(matching) or matching[0]


def find_blank_page(context: BrowserContext):
    """Return an existing about:blank tab, if one exists."""
    for page in context.pages:
        if page.url == "about:blank":
            return page
    return None


def get_or_open_domain_page(context: BrowserContext, domain: str, url: str):
    """
    Generic tab-reuse primitive used by both 'open' and YouTube-specific flows.

    - If a tab for `domain` already exists: focus it, return (page, True),
      and never reload/navigate it.
    - Otherwise: open `url` in a blank tab (or a brand new tab), focus it,
      return (page, False).
    """
    existing = find_page_by_domain(context, domain)
    if existing:
        focus_page(existing)
        try:
            from nova.browser.manager import BrowserManager
            BrowserManager.focus_active_window()
        except Exception:
            pass
        return existing, True

    page = find_blank_page(context) or context.new_page()
    focus_page(page)
    try:
        from nova.browser.manager import BrowserManager
        BrowserManager.focus_active_window()
    except Exception:
        pass
    page.goto(url, timeout=30000)
    wait_for_page_ready(page)
    return page, False


# ---------------------------------------------------------------------------
# Form / input helpers
# ---------------------------------------------------------------------------

def type_into_field(page: Page, locator, value: str, delay: int = 50) -> None:
    """
    Clear and type into a focused field using real keyboard interaction
    (click -> Ctrl+A -> Backspace -> type) instead of .fill(""), which is
    more reliable against JS-managed inputs (e.g. YouTube's search box).
    """
    locator.click()
    locator.focus()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    locator.type(str(value), delay=delay)


def smart_fill(page: Page, selector: str, value: str) -> None:
    """
    Fill a form field robustly, handling both standard inputs and
    contenteditable/div-based inputs (common in modern web apps).
    """
    from nova.browser.interaction import BrowserInteractionHelper
    
    def do_fill(loc):
        tag = loc.evaluate("el => el.tagName").lower()
        is_editable = loc.evaluate(
            "el => el.contentEditable === 'true' || "
            "el.getAttribute('contenteditable') === 'true'"
        )
        if tag == "div" or is_editable:
            type_into_field(page, loc, value)
        else:
            loc.fill("")
            loc.type(str(value))
            
    try:
        BrowserInteractionHelper.execute_interaction(
            page=page,
            query=selector,
            action_type="type",
            action_fn=do_fill,
            max_retries=3
        )
    except Exception as e:
        try:
            type_into_field(page, page.locator(selector).first, value)
        except Exception as e2:
            raise Exception(f"Failed to fill field '{selector}': {e} (Fallback failed: {e2})")


# ---------------------------------------------------------------------------
# YouTube-specific helpers
# ---------------------------------------------------------------------------

def get_or_open_youtube_page(context: BrowserContext):
    """Reuse an existing YouTube tab, or open one. See get_or_open_domain_page."""
    return get_or_open_domain_page(context, YOUTUBE_DOMAIN, "https://www.youtube.com")


def search_youtube(page: Page, query: str) -> tuple:
    """
    Run a search on an already-open YouTube page, click the first result,
    and confirm the watch page has actually started loading before
    reporting success. Returns (success, video_title_or_error_message).
    """
    try:
        page.wait_for_selector(YOUTUBE_SEARCH_BOX_SELECTOR, timeout=15000)
        search_input = page.locator(YOUTUBE_SEARCH_BOX_SELECTOR)

        type_into_field(page, search_input, query)
        page.keyboard.press("Enter")

        page.wait_for_selector(YOUTUBE_VIDEO_RESULT_SELECTOR, timeout=15000)

        first_video = page.locator(YOUTUBE_VIDEO_RESULT_SELECTOR).first
        video_title = first_video.inner_text().strip()
        first_video.click()

        # Confirm navigation to the watch page has actually begun, rather
        # than immediately reporting success right after the click.
        try:
            page.wait_for_url(YOUTUBE_WATCH_URL_PATTERN, timeout=10000)
        except Exception:
            pass
        wait_for_page_ready(page, timeout=10000)

        return True, video_title
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------
# Each handler receives the BrowserContext and the raw params dict, and
# returns a plain dict (never prints directly) with a consistent shape:
#   {"status": "success"/"error", "message": "...", ...extra fields}

REUSE_DOMAINS = ["youtube.com", "chatgpt.com", "github.com"]

def handle_open(context: BrowserContext, params: dict) -> dict:
    url = (params.get("url") or "").strip()
    if not url:
        return {"status": "error", "message": "No URL provided for open operation"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    matched_domain = None
    for domain in REUSE_DOMAINS:
        if url_belongs_to_domain(url, domain):
            matched_domain = domain
            break

    if matched_domain:
        page, was_open = get_or_open_domain_page(context, matched_domain, url)
        message = (
            f"Successfully focused existing {matched_domain} tab"
            if was_open
            else f"Successfully navigated to {url}"
        )
        return {"status": "success", "message": message, "title": page.title()}

    # Non-matching open: reuse the active tab if blank, otherwise open a new one.
    page = find_active_page(context)
    if page.url != "about:blank":
        page = context.new_page()
    focus_page(page)

    page.goto(url, timeout=30000)
    wait_for_page_ready(page)
    return {
        "status": "success",
        "message": f"Successfully navigated to {url}",
        "title": page.title(),
    }


def handle_search_youtube(context: BrowserContext, params: dict) -> dict:
    query = (params.get("query") or "").strip()
    if not query:
        return {"status": "error", "message": "No query provided for YouTube search"}

    page, _ = get_or_open_youtube_page(context)

    success, result = search_youtube(page, query)
    if success:
        return {"status": "success", "message": f"Playing video: '{result}' on YouTube"}
    return {"status": "error", "message": f"Failed to play video on YouTube: {result}"}


def handle_fill_form(context: BrowserContext, params: dict) -> dict:
    page = find_active_page(context)
    focus_page(page)

    form_data = params.get("form_data")
    if form_data:
        for selector, val in form_data.items():
            smart_fill(page, selector, str(val))
        return {"status": "success", "message": f"Successfully filled {len(form_data)} form fields"}

    selector = params.get("selector")
    value = params.get("value")
    if not selector or value is None:
        return {"status": "error", "message": "Missing selector or value for fill_form"}

    smart_fill(page, selector, str(value))
    return {
        "status": "success",
        "message": f"Successfully filled field '{selector}' with '{value}'",
    }


def handle_click(context: BrowserContext, params: dict) -> dict:
    from nova.browser.interaction import BrowserInteractionHelper
    page = find_active_page(context)
    focus_page(page)

    selector = params.get("selector")
    if not selector:
        return {"status": "error", "message": "No selector provided for click operation"}

    try:
        BrowserInteractionHelper.execute_interaction(
            page=page,
            query=selector,
            action_type="click",
            action_fn=lambda loc: loc.click(timeout=5000),
            max_retries=3
        )
    except Exception as e:
        url_lower = (page.url or "").lower()
        if "chatgpt.com" in url_lower and any(k in selector.lower() for k in ("submit", "send", "message")):
            return {"status": "success", "message": f"Prompt already submitted, click on '{selector}' bypassed"}
        raise e
    return {"status": "success", "message": f"Successfully clicked element '{selector}'"}


def handle_get_content(context: BrowserContext, params: dict) -> dict:
    page = find_active_page(context)
    body_text = page.locator("body").inner_text()
    return {
        "status": "success",
        "title": page.title(),
        "url": page.url,
        "text": body_text[:1000],
    }


OPERATION_HANDLERS = {
    "open": handle_open,
    "search_youtube": handle_search_youtube,
    "fill_form": handle_fill_form,
    "click": handle_click,
    "get_content": handle_get_content,
}


# ---------------------------------------------------------------------------
# Browser Context Awareness Handlers
# ---------------------------------------------------------------------------

class WebsiteContextHandler:
    domains = []

    def can_handle(self, page: Page, query: str, params: dict) -> bool:
        """Return True if this command applies to the current website."""
        raise NotImplementedError()

    def handle(self, page: Page, query: str, params: dict) -> dict:
        """Execute the command directly on the active page."""
        raise NotImplementedError()


class YouTubeHandler(WebsiteContextHandler):
    domains = ["youtube.com"]

    def can_handle(self, page: Page, query: str, params: dict) -> bool:
        op = params.get("operation", "")
        if op not in ("fill_form", "search_youtube"):
            return False
        return op == "search_youtube" or any(k in query.lower() for k in ("play", "song", "music", "artist", "youtube", "watch"))

    def handle(self, page: Page, query: str, params: dict) -> dict:
        search_query = params.get("query") or params.get("value") or query
        search_query = re.sub(r'^(play|search|watch|look up|find)\s+(on youtube|youtube)?\s*', '', search_query, flags=re.IGNORECASE).strip()
        
        # Emit youtube_search to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("youtube_search", module="browser", status="running", metadata={"query": search_query})
        except Exception:
            pass

        success, title = search_youtube(page, search_query)
        
        # Emit youtube_search status to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("youtube_search", module="browser", status="success" if success else "failed", metadata={"query": search_query, "title": title if success else "", "error": "" if success else title})
        except Exception:
            pass

        if success:
            return {"status": "success", "message": f"Playing video: '{title}' on YouTube"}
        return {"status": "error", "message": f"Failed to play video on YouTube: {title}"}


class ChatGPTHandler(WebsiteContextHandler):
    domains = ["chatgpt.com"]

    def can_handle(self, page: Page, query: str, params: dict) -> bool:
        op = params.get("operation", "")
        if op != "fill_form":
            return False
        return any(k in query.lower() for k in ("ask", "prompt", "tell", "write", "say", "type", "send", "chatgpt", "gpt"))

    def handle(self, page: Page, query: str, params: dict) -> dict:
        from nova.browser.interaction import BrowserInteractionHelper
        prompt_text = params.get("value") or params.get("query") or query
        prompt_text = re.sub(r'^(ask|prompt|tell|write|say|type|send)\s+(chatgpt|gpt)?\s*', '', prompt_text, flags=re.IGNORECASE).strip()
        
        selector = "#prompt-textarea"
        smart_fill(page, selector, prompt_text)
        
        def do_click(loc):
            return loc.click(timeout=3000)
            
        try:
            BrowserInteractionHelper.execute_interaction(
                page=page,
                query="[aria-label='Send prompt'], button[data-testid*='send'], Send",
                action_type="click",
                action_fn=do_click,
                max_retries=2
            )
        except Exception:
            page.keyboard.press("Enter")
            
        return {"status": "success", "message": f"Sent prompt to ChatGPT: '{prompt_text}'"}


class GmailHandler(WebsiteContextHandler):
    domains = ["mail.google.com", "gmail.com"]

    def can_handle(self, page: Page, query: str, params: dict) -> bool:
        op = params.get("operation", "")
        if op != "fill_form":
            return False
        return any(k in query.lower() for k in ("search", "find", "email", "mail", "gmail"))

    def handle(self, page: Page, query: str, params: dict) -> dict:
        search_query = params.get("query") or params.get("value") or query
        search_query = re.sub(r'^(search|find|filter)\s+(email|emails|mail|gmail)?\s*', '', search_query, flags=re.IGNORECASE).strip()
        
        selector = "input[name='q']"
        smart_fill(page, selector, search_query)
        page.keyboard.press("Enter")
        wait_for_page_ready(page)
        return {"status": "success", "message": f"Searched Gmail for: '{search_query}'"}


class GoogleDocsHandler(WebsiteContextHandler):
    domains = ["docs.google.com"]

    def can_handle(self, page: Page, query: str, params: dict) -> bool:
        op = params.get("operation", "")
        if op != "fill_form":
            return False
        return any(k in query.lower() for k in ("type", "write", "insert", "append", "text", "doc"))

    def handle(self, page: Page, query: str, params: dict) -> dict:
        from nova.browser.interaction import BrowserInteractionHelper
        text_to_type = params.get("value") or params.get("query") or query
        text_to_type = re.sub(r'^(type|write|insert|append)\s+(text|into doc|doc)?\s*', '', text_to_type, flags=re.IGNORECASE).strip()
        
        selector = ".docs-texteventtarget"
        def do_type(loc):
            loc.focus()
            page.keyboard.type(text_to_type)
            
        BrowserInteractionHelper.execute_interaction(
            page=page,
            query=selector,
            action_type="type",
            action_fn=do_type,
            max_retries=3
        )
        return {"status": "success", "message": f"Typed text into Google Doc: '{text_to_type}'"}


class GitHubHandler(WebsiteContextHandler):
    domains = ["github.com"]

    def can_handle(self, page: Page, query: str, params: dict) -> bool:
        op = params.get("operation", "")
        if op != "fill_form":
            return False
        return any(k in query.lower() for k in ("search", "find", "lookup", "repo", "repository", "github"))

    def handle(self, page: Page, query: str, params: dict) -> dict:
        from nova.browser.interaction import BrowserInteractionHelper
        search_query = params.get("query") or params.get("value") or query
        search_query = re.sub(r'^(search|find|lookup|open)\s+(repo|repository|github)?\s*', '', search_query, flags=re.IGNORECASE).strip()
        
        try:
            if not page.locator("input#query-builder-test").is_visible():
                BrowserInteractionHelper.execute_interaction(
                    page=page,
                    query="button.header-search-button, Search",
                    action_type="click",
                    action_fn=lambda loc: loc.click(timeout=3000),
                    max_retries=2
                )
        except Exception:
            pass
        
        selector = "input#query-builder-test"
        smart_fill(page, selector, search_query)
        page.keyboard.press("Enter")
        wait_for_page_ready(page)
        return {"status": "success", "message": f"Searched GitHub for: '{search_query}'"}


class GoogleSearchHandler(WebsiteContextHandler):
    domains = ["google.com"]

    def can_handle(self, page: Page, query: str, params: dict) -> bool:
        op = params.get("operation", "")
        if op != "fill_form":
            return False
        url_lower = (page.url or "").lower()
        if "/docs" in url_lower or "/mail" in url_lower:
            return False
        return any(k in query.lower() for k in ("search", "find", "lookup", "google", "look up"))

    def handle(self, page: Page, query: str, params: dict) -> dict:
        search_query = params.get("query") or params.get("value") or query
        search_query = re.sub(r'^(search|find|lookup|look up|google)\s*', '', search_query, flags=re.IGNORECASE).strip()
        
        selector = "textarea[name='q']"
        smart_fill(page, selector, search_query)
        page.keyboard.press("Enter")
        wait_for_page_ready(page)
        return {"status": "success", "message": f"Searched Google for: '{search_query}'"}


CONTEXT_HANDLERS = [
    YouTubeHandler(),
    ChatGPTHandler(),
    GmailHandler(),
    GoogleDocsHandler(),
    GitHubHandler(),
    GoogleSearchHandler()
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_automation(params: dict) -> dict:
    operation = (params.get("operation") or "open").strip().lower()
    query = (params.get("_user_query") or "").strip()

    handler = OPERATION_HANDLERS.get(operation)
    if handler is None:
        try:
            from nova.browser.engine import BrowserAutomationEngine
            engine = BrowserAutomationEngine()
            if operation in engine._actions:
                return engine.execute_action(operation, params)
        except Exception as e:
            return {"status": "error", "message": f"Generic browser engine initialization failed: {e}"}
        return {"status": "error", "message": f"Unsupported operation: {operation}"}

    try:
        try:
            browser = BrowserManager.get_browser()
        except Exception as e:
            return {
                "status": "error",
                "message": (
                    f"Could not connect to Chromium debugging port {BrowserManager.PORT}. "
                    f"Make sure Chromium is running in debugging mode. Error: {e}"
                ),
            }

        context = BrowserManager.get_persistent_context(browser)

        # --- Browser Context Awareness ---
        # Query the active page and check if a domain-specific handler applies
        try:
            page = find_active_page(context)
            url_lower = (page.url or "").lower()
            
            matched_handler = None
            if operation != "click":
                for h in CONTEXT_HANDLERS:
                    if any(domain in url_lower for domain in h.domains):
                        matched_handler = h
                        break
                
                # If no active page matched a handler, check if the query specifically targets a handler's domain
                if not matched_handler and query:
                    for h in CONTEXT_HANDLERS:
                        # Define domain aliases for common typos and variations
                        aliases = [d.split('.')[0] for d in h.domains]
                        if "chatgpt.com" in h.domains:
                            aliases.extend(["chatgpt", "gpt", "chagpt", "chagtpt", "chatgt", "openai"])
                        elif "youtube.com" in h.domains:
                            aliases.extend(["youtube", "utube", "yt"])
                        elif "mail.google.com" in h.domains or "gmail.com" in h.domains:
                            aliases.extend(["gmail", "email", "mail"])
                        elif "docs.google.com" in h.domains:
                            aliases.extend(["docs", "doc"])
                        elif "github.com" in h.domains:
                            aliases.extend(["github", "git"])
                        elif "google.com" in h.domains:
                            aliases.extend(["google", "search"])
                            
                        if any(alias in query.lower() for alias in aliases):
                            matched_handler = h
                            # Dynamically open that domain page first!
                            target_domain = h.domains[0]
                            target_url = f"https://{target_domain}"
                            if target_domain == "gmail.com":
                                target_url = "https://mail.google.com"
                            page, _ = get_or_open_domain_page(context, target_domain, target_url)
                            break
                    
            if matched_handler and matched_handler.can_handle(page, query, params):
                return matched_handler.handle(page, query, params)
        except Exception as e:
            pass

        try:
            return handler(context, params)
        except Exception as e:
            return {"status": "error", "message": f"Browser automation action failed: {e}"}

    except Exception as e:
        return {"status": "error", "message": f"Browser automation failed to start: {e}"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Missing parameter argument"}))
        sys.exit(1)

    try:
        raw_params = json.loads(sys.argv[1])
    except Exception:
        print(json.dumps({"status": "error", "message": "Failed to parse input parameters"}))
        sys.exit(1)

    result = run_automation(raw_params)
    print(json.dumps(result))