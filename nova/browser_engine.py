import os
import time
import re
import json
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from playwright.sync_api import Page, BrowserContext, Locator, Browser

class BrowserActionException(Exception):
    """Custom exception raised when a browser action fails."""
    pass

class BaseBrowserAction(ABC):
    """Abstract base class for all browser actions."""
    
    @abstractmethod
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the action on the target page/context.
        Returns a dict indicating the result, e.g., {"status": "success", "message": "..."}
        """
        pass

# ---------------------------------------------------------------------------
# Intelligent Element Detection Engine
# ---------------------------------------------------------------------------

DETECT_SCRIPT = """
(query, actionType) => {
    const normalize = (val) => {
        if (!val) return "";
        return String(val).toLowerCase().trim().replace(/\\s+/g, " ");
    };
    
    const cleanQuery = normalize(query);
    if (!cleanQuery) return [];
    
    const getXPath = (element) => {
        if (element.id) {
            return `//*[@id="${element.id}"]`;
        }
        if (element === document.body) {
            return '/html/body';
        }
        let ix = 0;
        const siblings = element.parentNode ? element.parentNode.childNodes : [];
        for (let i = 0; i < siblings.length; i++) {
            const sibling = siblings[i];
            if (sibling === element) {
                return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
            }
            if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                ix++;
            }
        }
        return '';
    };

    const getLabelText = (el) => {
        if (el.getAttribute("aria-label")) return el.getAttribute("aria-label");
        const labelledBy = el.getAttribute("aria-labelledby");
        if (labelledBy) {
            const labelEl = document.getElementById(labelledBy);
            if (labelEl) return labelEl.innerText;
        }
        if (el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) return label.innerText;
        }
        let parent = el.parentNode;
        while (parent) {
            if (parent.tagName === 'LABEL') {
                return parent.innerText;
            }
            parent = parent.parentNode;
        }
        return "";
    };

    const elements = Array.from(document.querySelectorAll('input, button, textarea, select, a, [role="button"], [role="link"], [role="checkbox"], [role="textbox"], [onclick]'));
    const candidates = [];
    
    for (const el of elements) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        if (el.disabled) continue;
        
        const tagName = el.tagName.toLowerCase();
        const role = el.getAttribute("role") || "";
        const typeAttr = el.getAttribute("type") || "";
        
        let roleScore = 0;
        if (actionType === 'type') {
            const isTextInput = (tagName === 'input' && (!typeAttr || ['text', 'search', 'email', 'url', 'tel', 'password', 'number'].includes(typeAttr.toLowerCase())))
                                || tagName === 'textarea' || role === 'textbox';
            if (isTextInput) roleScore = 100;
        } else if (actionType === 'click') {
            const isClickable = tagName === 'button' || tagName === 'a' || role === 'button' || role === 'link' || role === 'checkbox' || role === 'radio'
                                || ['submit', 'button', 'checkbox', 'radio', 'image'].includes(typeAttr.toLowerCase())
                                || el.hasAttribute('onclick');
            if (isClickable) roleScore = 100;
        }
        
        const labelText = normalize(getLabelText(el));
        let labelScore = 0;
        if (labelText) {
            if (labelText === cleanQuery) labelScore = 80;
            else if (labelText.includes(cleanQuery)) labelScore = 40;
        }
        
        const placeholder = normalize(el.getAttribute("placeholder"));
        let placeholderScore = 0;
        if (placeholder) {
            if (placeholder === cleanQuery) placeholderScore = 70;
            else if (placeholder.includes(cleanQuery)) placeholderScore = 35;
        }
        
        let ariaScore = 0;
        const ariaDescribedBy = normalize(el.getAttribute("aria-describedby"));
        const ariaKeys = normalize(el.getAttribute("aria-keyshortcuts"));
        const ariaDetails = normalize(el.getAttribute("aria-details"));
        const ariaPlaceholder = normalize(el.getAttribute("aria-placeholder"));
        const combinedAria = `${ariaDescribedBy} ${ariaKeys} ${ariaDetails} ${ariaPlaceholder}`;
        if (combinedAria.trim()) {
            if (combinedAria.includes(cleanQuery)) ariaScore = 60;
        }
        
        let nameScore = 0;
        const nameAttr = normalize(el.getAttribute("name"));
        const idAttr = normalize(el.id);
        if (nameAttr === cleanQuery || idAttr === cleanQuery) {
            nameScore = 50;
        } else if (nameAttr.includes(cleanQuery) || idAttr.includes(cleanQuery)) {
            nameScore = 25;
        }
        
        let textScore = 0;
        const visibleText = normalize(el.innerText || el.textContent);
        if (visibleText) {
            if (visibleText === cleanQuery) textScore = 40;
            else if (visibleText.includes(cleanQuery)) textScore = 20;
        }
        
        let cssScore = 0;
        const classNames = normalize(el.className);
        if (classNames && classNames.includes(cleanQuery)) {
            cssScore = 10;
        }
        
        const totalScore = roleScore + labelScore + placeholderScore + ariaScore + nameScore + textScore + cssScore;
        
        if (totalScore > 0) {
            const attrs = {};
            for (let i = 0; i < el.attributes.length; i++) {
                attrs[el.attributes[i].name] = el.attributes[i].value;
            }
            candidates.push({
                xpath: getXPath(el),
                tag: tagName,
                text: el.innerText || el.textContent || "",
                visible: true,
                attributes: attrs,
                box: {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                },
                score: totalScore,
                scores: {
                    role: roleScore,
                    label: labelScore,
                    placeholder: placeholderScore,
                    aria: ariaScore,
                    name: nameScore,
                    text: textScore,
                    css: cssScore
                }
            });
        }
    }
    
    candidates.sort((a, b) => b.score - a.score);
    return candidates;
}
"""

class IntelligentElementDetectionEngine:
    """Intelligent Element Detection Engine using semantic element ranking."""
    
    def is_raw_selector(self, query: str) -> bool:
        s = query.strip()
        if s.startswith(("/", "xpath=", "./", "(")):
            return True
        if any(c in s for c in ("#", ".", "[", "]", ">", ":", "=")):
            return True
        return False
        
    def detect_element(self, page: Page, query: str, action_type: str) -> Locator:
        if not query:
            raise BrowserActionException("Query cannot be empty for element detection")
            
        # 1. Direct CSS/XPath selector check
        if self.is_raw_selector(query):
            return page.locator(query)
            
        # 2. Try browser-side JS candidate ranking
        try:
            candidates = page.evaluate(DETECT_SCRIPT, [query, action_type])
            if candidates:
                best_candidate = candidates[0]
                xpath = best_candidate["xpath"]
                return page.locator(f"xpath={xpath}")
        except Exception:
            pass
            
        # 3. Native Playwright fallback search
        try:
            loc = page.get_by_placeholder(query, exact=False)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass
            
        try:
            loc = page.get_by_text(query, exact=False)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass
            
        return page.locator(query)
        
    def detect_all_elements(self, page: Page, query: str) -> List[Dict[str, Any]]:
        if self.is_raw_selector(query):
            return []
        try:
            return page.evaluate(DETECT_SCRIPT, [query, "click"])
        except Exception:
            return []

# ---------------------------------------------------------------------------
# Reusable Action Classes
# ---------------------------------------------------------------------------

class NavigateAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        url = params.get("url") or params.get("value")
        if not url:
            raise BrowserActionException("Missing required parameter 'url'")
        
        url = str(url).strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            
        timeout = params.get("timeout", 30000)
        wait_until = params.get("wait_until", "load")
        
        page = engine.get_active_page()
        try:
            page.goto(url, timeout=float(timeout), wait_until=wait_until)
            return {
                "status": "success",
                "message": f"Successfully navigated to {url}",
                "url": page.url,
                "title": page.title()
            }
        except Exception as e:
            raise BrowserActionException(f"Navigation to {url} failed: {e}")

class RefreshAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        timeout = params.get("timeout", 30000)
        wait_until = params.get("wait_until", "load")
        
        page = engine.get_active_page()
        try:
            page.reload(timeout=float(timeout), wait_until=wait_until)
            return {
                "status": "success",
                "message": "Successfully refreshed the page",
                "url": page.url
            }
        except Exception as e:
            raise BrowserActionException(f"Refresh failed: {e}")

class ClickAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        selector = params.get("selector")
        if not selector:
            raise BrowserActionException("Missing required parameter 'selector'")
            
        timeout = params.get("timeout", 15000)
        click_count = params.get("click_count", 1)
        button = params.get("button", "left")
        modifiers = params.get("modifiers")
        force = params.get("force", False)
        no_wait_after = params.get("no_wait_after", False)
        
        try:
            def do_click(loc):
                return loc.click(
                    timeout=float(timeout) / 3.0,
                    click_count=int(click_count),
                    button=button,
                    modifiers=modifiers,
                    force=bool(force),
                    no_wait_after=bool(no_wait_after)
                )
            engine.interact_with_retry(str(selector), "click", do_click, timeout=float(timeout))
            return {
                "status": "success",
                "message": f"Successfully clicked element '{selector}'"
            }
        except Exception as e:
            raise BrowserActionException(f"Click on '{selector}' failed: {e}")

class TypeAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        selector = params.get("selector")
        if not selector:
            raise BrowserActionException("Missing required parameter 'selector'")
            
        text = params.get("text") or params.get("value")
        if text is None:
            raise BrowserActionException("Missing required parameter 'text' or 'value'")
            
        timeout = params.get("timeout", 15000)
        delay = params.get("delay", 0)
        clear = params.get("clear", True)
        click_first = params.get("click_first", True)
        
        page = engine.get_active_page()
        try:
            def do_type(loc):
                if click_first:
                    loc.click(timeout=float(timeout) / 3.0)
                if clear:
                    try:
                        loc.fill("", timeout=float(timeout) / 3.0)
                    except Exception:
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                return loc.type(str(text), delay=float(delay), timeout=float(timeout) / 3.0)
                
            engine.interact_with_retry(str(selector), "type", do_type, timeout=float(timeout))
            return {
                "status": "success",
                "message": f"Successfully typed text into element '{selector}'"
            }
        except Exception as e:
            raise BrowserActionException(f"Typing into '{selector}' failed: {e}")

class HoverAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        selector = params.get("selector")
        if not selector:
            raise BrowserActionException("Missing required parameter 'selector'")
            
        timeout = params.get("timeout", 15000)
        force = params.get("force", False)
        
        try:
            def do_hover(loc):
                return loc.hover(timeout=float(timeout) / 3.0, force=bool(force))
            engine.interact_with_retry(str(selector), "click", do_hover, timeout=float(timeout))
            return {
                "status": "success",
                "message": f"Successfully hovered over element '{selector}'"
            }
        except Exception as e:
            raise BrowserActionException(f"Hover on '{selector}' failed: {e}")

class ScrollAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        direction = str(params.get("direction", "down")).strip().lower()
        if direction not in ("up", "down", "left", "right"):
            raise BrowserActionException(f"Invalid direction '{direction}'. Must be one of up, down, left, right.")
            
        amount = params.get("amount")
        if amount is not None:
            amount = int(amount)
            
        selector = params.get("selector")
        page = engine.get_active_page()
        
        try:
            if selector:
                def do_scroll(loc):
                    nonlocal amount
                    if amount is None:
                        if direction in ("up", "down"):
                            amount = loc.evaluate("(el) => el.clientHeight")
                        else:
                            amount = loc.evaluate("(el) => el.clientWidth")
                    
                    if direction == "down":
                        loc.evaluate("(el, amt) => el.scrollTop += amt", amount)
                    elif direction == "up":
                        loc.evaluate("(el, amt) => el.scrollTop -= amt", amount)
                    elif direction == "right":
                        loc.evaluate("(el, amt) => el.scrollLeft += amt", amount)
                    elif direction == "left":
                        loc.evaluate("(el, amt) => el.scrollLeft -= amt", amount)
                    return amount
                    
                amount = engine.interact_with_retry(str(selector), "click", do_scroll)
                target_desc = f"element '{selector}'"
            else:
                if amount is None:
                    if direction in ("up", "down"):
                        amount = page.evaluate("window.innerHeight")
                    else:
                        amount = page.evaluate("window.innerWidth")
                        
                if direction == "down":
                    page.evaluate(f"window.scrollBy(0, {amount})")
                elif direction == "up":
                    page.evaluate(f"window.scrollBy(0, -{amount})")
                elif direction == "right":
                    page.evaluate(f"window.scrollBy({amount}, 0)")
                elif direction == "left":
                    page.evaluate(f"window.scrollBy(-{amount}, 0)")
                    
                target_desc = "window"
                
            return {
                "status": "success",
                "message": f"Successfully scrolled {target_desc} {direction} by {amount} pixels"
            }
        except Exception as e:
            raise BrowserActionException(f"Scroll operation failed: {e}")

class DragAndDropAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        source_selector = params.get("source_selector") or params.get("selector")
        target_selector = params.get("target_selector") or params.get("value")
        
        if not source_selector or not target_selector:
            raise BrowserActionException("Missing required parameter 'source_selector' (or 'selector') or 'target_selector' (or 'value')")
            
        timeout = params.get("timeout", 15000)
        force = params.get("force", False)
        
        page = engine.get_active_page()
        try:
            target_locator = engine.resolve_locator(page, str(target_selector), "click")
            def do_drag(loc):
                return loc.drag_to(target_locator, timeout=float(timeout) / 3.0, force=bool(force))
                
            engine.interact_with_retry(str(source_selector), "click", do_drag, timeout=float(timeout))
            return {
                "status": "success",
                "message": f"Successfully dragged '{source_selector}' and dropped onto '{target_selector}'"
            }
        except Exception as e:
            raise BrowserActionException(f"Drag and drop from '{source_selector}' to '{target_selector}' failed: {e}")

class UploadFileAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        selector = params.get("selector")
        file_paths = params.get("file_paths") or params.get("value") or params.get("url")
        
        if not selector or not file_paths:
            raise BrowserActionException("Missing required parameter 'selector' or 'file_paths' ('value')")
            
        if isinstance(file_paths, str):
            if "," in file_paths:
                file_paths = [f.strip() for f in file_paths.split(",")]
            else:
                file_paths = [file_paths]
                
        abs_paths = [os.path.abspath(str(p)) for p in file_paths]
        
        for p in abs_paths:
            if not os.path.exists(p):
                raise BrowserActionException(f"Upload failed: File does not exist at '{p}'")
                
        timeout = params.get("timeout", 15000)
        try:
            def do_upload(loc):
                return loc.set_input_files(abs_paths, timeout=float(timeout) / 3.0)
            engine.interact_with_retry(str(selector), "type", do_upload, timeout=float(timeout))
            return {
                "status": "success",
                "message": f"Successfully uploaded {len(abs_paths)} file(s) to '{selector}'"
            }
        except Exception as e:
            raise BrowserActionException(f"File upload to '{selector}' failed: {e}")

class DownloadFileAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        click_selector = params.get("click_selector") or params.get("selector")
        if not click_selector:
            raise BrowserActionException("Missing required parameter 'click_selector' (or 'selector')")
            
        download_dir = params.get("download_dir") or os.path.expanduser("~/Downloads")
        timeout = params.get("timeout", 30000)
        
        page = engine.get_active_page()
        try:
            os.makedirs(download_dir, exist_ok=True)
            def do_download(loc):
                with page.expect_download(timeout=float(timeout) / 3.0) as download_info:
                    loc.click()
                return download_info.value
                
            download = engine.interact_with_retry(str(click_selector), "click", do_download, timeout=float(timeout))
            suggested_filename = download.suggested_filename
            dest_path = os.path.join(download_dir, suggested_filename)
            download.save_as(dest_path)
            
            return {
                "status": "success",
                "message": f"Successfully downloaded file '{suggested_filename}' to '{download_dir}'",
                "suggested_filename": suggested_filename,
                "path": dest_path
            }
        except Exception as e:
            raise BrowserActionException(f"Download triggered by click on '{click_selector}' failed: {e}")

class PressKeysAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        key = params.get("key") or params.get("value")
        if not key:
            raise BrowserActionException("Missing required parameter 'key' (or 'value')")
            
        selector = params.get("selector")
        delay = params.get("delay", 0)
        timeout = params.get("timeout", 15000)
        
        page = engine.get_active_page()
        try:
            def do_press(loc):
                loc.focus(timeout=float(timeout) / 3.0)
                return page.keyboard.press(str(key), delay=float(delay))
                
            if selector:
                engine.interact_with_retry(str(selector), "click", do_press, timeout=float(timeout))
            else:
                page.keyboard.press(str(key), delay=float(delay))
                
            return {
                "status": "success",
                "message": f"Successfully pressed key(s) '{key}'" + (f" on element '{selector}'" if selector else "")
            }
        except Exception as e:
            raise BrowserActionException(f"Pressing key(s) '{key}' failed: {e}")

class WaitAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        seconds = params.get("seconds") or params.get("value")
        selector = params.get("selector")
        
        if seconds is None and not selector:
            raise BrowserActionException("Specify either 'seconds' (or 'value') for static sleep or a 'selector' to wait for")
            
        timeout = params.get("timeout", 15000)
        state = params.get("state", "visible")
        if state not in ("attached", "detached", "visible", "hidden"):
            raise BrowserActionException(f"Invalid state '{state}'. Must be one of attached, detached, visible, hidden.")
            
        page = engine.get_active_page()
        try:
            if seconds is not None:
                sleep_ms = float(seconds) * 1000
                page.wait_for_timeout(sleep_ms)
                return {
                    "status": "success",
                    "message": f"Successfully waited for {seconds} seconds"
                }
            else:
                def do_wait(loc):
                    return loc.wait_for(state=state, timeout=float(timeout) / 3.0)
                engine.interact_with_retry(str(selector), "click", do_wait, timeout=float(timeout))
                return {
                    "status": "success",
                    "message": f"Successfully waited for element '{selector}' to be {state}"
                }
        except Exception as e:
            raise BrowserActionException(f"Wait operation failed: {e}")

class ReadTextAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        selector = params.get("selector", "body")
        mode = params.get("mode", "inner_text").lower()
        attribute_name = params.get("attribute_name") or params.get("attribute")
        timeout = params.get("timeout", 15000)
        
        try:
            if selector and selector != "body":
                def do_read(loc):
                    if mode == "inner_text":
                        return loc.inner_text(timeout=float(timeout) / 3.0)
                    elif mode == "text_content":
                        return loc.text_content(timeout=float(timeout) / 3.0) or ""
                    elif mode == "attribute":
                        if not attribute_name:
                            raise BrowserActionException("Missing required parameter 'attribute_name' for 'attribute' mode")
                        return loc.get_attribute(str(attribute_name), timeout=float(timeout) / 3.0) or ""
                    elif mode == "all_text":
                        return loc.inner_text(timeout=float(timeout) / 3.0)
                    return ""
                text = engine.interact_with_retry(str(selector), "click", do_read, timeout=float(timeout))
            else:
                page = engine.get_active_page()
                locator = page.locator("body")
                if mode == "inner_text":
                    text = locator.first.inner_text(timeout=float(timeout))
                elif mode == "text_content":
                    text = locator.first.text_content(timeout=float(timeout)) or ""
                elif mode == "attribute":
                    if not attribute_name:
                        raise BrowserActionException("Missing required parameter 'attribute_name' for 'attribute' mode")
                    text = locator.first.get_attribute(str(attribute_name), timeout=float(timeout)) or ""
                elif mode == "all_text":
                    count = locator.count()
                    texts = [locator.nth(i).inner_text(timeout=float(timeout)) for i in range(count)]
                    text = "\n".join(texts)
                else:
                    raise BrowserActionException(f"Invalid mode '{mode}'. Must be one of inner_text, text_content, attribute, all_text.")
                
            return {
                "status": "success",
                "text": text,
                "message": f"Successfully read text from '{selector}' in '{mode}' mode"
            }
        except Exception as e:
            raise BrowserActionException(f"Reading text from '{selector}' failed: {e}")

class FindElementsAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        selector = params.get("selector")
        if not selector:
            raise BrowserActionException("Missing required parameter 'selector'")
            
        timeout = params.get("timeout", 10000)
        page = engine.get_active_page()
        try:
            if not engine._detector.is_raw_selector(str(selector)):
                candidates = engine._detector.detect_all_elements(page, str(selector))
                return {
                    "status": "success",
                    "count": len(candidates),
                    "elements": candidates,
                    "message": f"Found {len(candidates)} semantic element(s) matching '{selector}'"
                }
                
            locator = page.locator(str(selector))
            try:
                locator.first.wait_for(state="attached", timeout=float(timeout))
            except Exception:
                pass
                
            count = locator.count()
            elements = []
            for i in range(count):
                el = locator.nth(i)
                info = el.evaluate('''
                    (el) => {
                        const rect = el.getBoundingClientRect();
                        const attrs = {};
                        for (let i = 0; i < el.attributes.length; i++) {
                            attrs[el.attributes[i].name] = el.attributes[i].value;
                        }
                        return {
                            tag: el.tagName.toLowerCase(),
                            text: el.innerText || el.textContent || "",
                            visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                            attributes: attrs,
                            box: {
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height
                            }
                        };
                    }
                ''')
                elements.append(info)
                
            return {
                "status": "success",
                "count": count,
                "elements": elements,
                "message": f"Found {count} element(s) matching '{selector}'"
            }
        except Exception as e:
            raise BrowserActionException(f"Finding elements matching '{selector}' failed: {e}")

class HandleTabsAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        operation = str(params.get("operation", "list")).strip().lower()
        if operation not in ("new", "close", "list", "switch"):
            raise BrowserActionException(f"Invalid tab operation '{operation}'. Must be one of new, close, list, switch.")
            
        context = engine.get_active_context()
        pages = context.pages
        
        try:
            if operation == "list":
                tabs = []
                active_page = engine.get_active_page(silent=True)
                for idx, pg in enumerate(pages):
                    tabs.append({
                        "index": idx,
                        "title": pg.title(),
                        "url": pg.url,
                        "active": (pg == active_page)
                    })
                return {
                    "status": "success",
                    "tabs": tabs,
                    "message": f"Successfully listed {len(tabs)} open tab(s)"
                }
                
            elif operation == "new":
                url = params.get("url")
                new_page = context.new_page()
                engine.set_active_page(new_page)
                msg = "Successfully opened new blank tab"
                
                if url:
                    url = str(url).strip()
                    if not url.startswith(("http://", "https://")):
                        url = "https://" + url
                    new_page.goto(url)
                    msg = f"Successfully opened new tab and navigated to {url}"
                    
                new_page.bring_to_front()
                return {
                    "status": "success",
                    "message": msg,
                    "title": new_page.title(),
                    "url": new_page.url
                }
                
            elif operation == "close":
                idx = params.get("index")
                target_page = None
                
                if idx is not None:
                    idx = int(idx)
                    if idx < 0 or idx >= len(pages):
                        raise BrowserActionException(f"Tab index {idx} out of range (0 to {len(pages)-1})")
                    target_page = pages[idx]
                else:
                    target_page = engine.get_active_page()
                    
                target_page.close()
                engine.clear_active_page_cache()
                return {
                    "status": "success",
                    "message": f"Successfully closed tab"
                }
                
            elif operation == "switch":
                idx = params.get("index")
                title_pattern = params.get("title_pattern") or params.get("value")
                target_page = None
                
                if idx is not None:
                    idx = int(idx)
                    if idx < 0 or idx >= len(pages):
                        raise BrowserActionException(f"Tab index {idx} out of range (0 to {len(pages)-1})")
                    target_page = pages[idx]
                elif title_pattern:
                    pattern = str(title_pattern).strip().lower()
                    for pg in pages:
                        if pattern in pg.title().lower() or pattern in pg.url.lower():
                            target_page = pg
                            break
                    if not target_page:
                        raise BrowserActionException(f"No tab found matching title/URL pattern: '{title_pattern}'")
                else:
                    raise BrowserActionException("Switch operation requires either an 'index' or a 'title_pattern' (or 'value')")
                    
                target_page.bring_to_front()
                engine.set_active_page(target_page)
                return {
                    "status": "success",
                    "message": f"Successfully switched to tab: '{target_page.title()}' ({target_page.url})"
                }
        except BrowserActionException:
            raise
        except Exception as e:
            raise BrowserActionException(f"Tab operation '{operation}' failed: {e}")

class HandleWindowsAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        operation = str(params.get("operation", "list")).strip().lower()
        if operation not in ("new", "close", "list", "switch"):
            raise BrowserActionException(f"Invalid window operation '{operation}'. Must be one of new, close, list, switch.")
            
        browser = engine.get_browser_instance()
        contexts = browser.contexts
        
        try:
            if operation == "list":
                windows = []
                active_ctx = engine.get_active_context()
                for idx, ctx in enumerate(contexts):
                    windows.append({
                        "index": idx,
                        "pages_count": len(ctx.pages),
                        "active": (ctx == active_ctx)
                    })
                return {
                    "status": "success",
                    "windows": windows,
                    "message": f"Successfully listed {len(windows)} open browser window(s)/context(s)"
                }
                
            elif operation == "new":
                new_ctx = browser.new_context()
                new_ctx.new_page()
                engine.set_active_context(new_ctx)
                return {
                    "status": "success",
                    "message": f"Successfully opened new browser window/context (index: {len(browser.contexts)-1})"
                }
                
            elif operation == "close":
                idx = params.get("index")
                target_ctx = None
                
                if idx is not None:
                    idx = int(idx)
                    if idx < 0 or idx >= len(contexts):
                        raise BrowserActionException(f"Window index {idx} out of range (0 to {len(contexts)-1})")
                    target_ctx = contexts[idx]
                else:
                    target_ctx = engine.get_active_context()
                    
                target_ctx.close()
                engine.clear_active_context_cache()
                return {
                    "status": "success",
                    "message": "Successfully closed browser window/context"
                }
                
            elif operation == "switch":
                idx = params.get("index")
                if idx is None:
                    raise BrowserActionException("Switch operation requires an 'index' parameter")
                    
                idx = int(idx)
                if idx < 0 or idx >= len(contexts):
                    raise BrowserActionException(f"Window index {idx} out of range (0 to {len(contexts)-1})")
                    
                target_ctx = contexts[idx]
                engine.set_active_context(target_ctx)
                if target_ctx.pages:
                    target_ctx.pages[0].bring_to_front()
                    
                return {
                    "status": "success",
                    "message": f"Successfully switched to browser window/context index {idx}"
                }
        except BrowserActionException:
            raise
        except Exception as e:
            raise BrowserActionException(f"Window operation '{operation}' failed: {e}")

class FillFormAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        fields = params.get("fields") or params.get("value")
        if not fields or not isinstance(fields, dict):
            raise BrowserActionException("Missing or invalid 'fields' parameter (must be a dictionary of label/value pairs)")
            
        timeout = params.get("timeout", 15000)
        for label, val in fields.items():
            engine.execute_action("type", {"selector": label, "text": val, "timeout": timeout})
            
        return {
            "status": "success",
            "message": f"Successfully filled {len(fields)} fields in form"
        }

class DetectLoginAction(BaseBrowserAction):
    def execute(self, engine: "BrowserAutomationEngine", params: Dict[str, Any]) -> Dict[str, Any]:
        page = engine.get_active_page()
        logged_in = engine.detect_login(page)
        return {
            "status": "success",
            "logged_in": logged_in,
            "message": f"Login state checked. Logged in: {logged_in}"
        }

class BrowserAutomationEngine:
    """Generic Browser Automation Engine coordinating page actions."""
    
    def __init__(self):
        self._actions: Dict[str, BaseBrowserAction] = {
            "navigate": NavigateAction(),
            "open": NavigateAction(),
            "refresh": RefreshAction(),
            "click": ClickAction(),
            "type": TypeAction(),
            "fill": TypeAction(),
            "fill_form": FillFormAction(),
            "hover": HoverAction(),
            "scroll": ScrollAction(),
            "drag_and_drop": DragAndDropAction(),
            "upload_file": UploadFileAction(),
            "download_file": DownloadFileAction(),
            "press_keys": PressKeysAction(),
            "press": PressKeysAction(),
            "wait": WaitAction(),
            "read_text": ReadTextAction(),
            "find_elements": FindElementsAction(),
            "handle_tabs": HandleTabsAction(),
            "handle_windows": HandleWindowsAction(),
            "detect_login": DetectLoginAction(),
        }
        
        self._detector = IntelligentElementDetectionEngine()
        self._active_context: Optional[BrowserContext] = None
        self._active_page: Optional[Page] = None
        
    def resolve_locator(self, page: Page, selector_or_query: str, action_type: str) -> Locator:
        """Resolves raw CSS/XPath or uses semantic Element Detection Engine."""
        from nova.browser_interaction_helper import BrowserInteractionHelper
        locs = BrowserInteractionHelper.get_alternative_locators(page, selector_or_query, action_type)
        if locs:
            active = BrowserInteractionHelper.select_active_element(locs)
            if active is not None:
                return active
            return locs[0]
        return self._detector.detect_element(page, selector_or_query, action_type)
        
    def recover_browser(self) -> None:
        """Attempts to recover/reconnect the browser and active context/page."""
        from nova.browser_manager import BrowserManager
        from nova.logger import logger
        logger.warning("Browser disconnect or target closed detected! Re-initializing Chromium session...")
        try:
            BrowserManager.close_connection()
        except Exception:
            pass
        self.clear_active_context_cache()
        self.clear_active_page_cache()
        
        self.get_browser_instance()
        self.get_active_context()
        self.get_active_page()
        logger.info("Browser session recovered successfully.")
        
    def interact_with_retry(
        self,
        selector_or_query: str,
        action_type: str,
        action_fn,
        timeout: float = 15000,
        max_retries: int = 3
    ) -> Any:
        """Runs the interaction function with automatic load waiting, checks, and retries."""
        from nova.browser_interaction_helper import BrowserInteractionHelper
        page = self.get_active_page()
        
        # Recover browser if closed/disconnected
        try:
            if not self.is_browser_running() or not self.get_browser_instance().is_connected():
                self.recover_browser()
                page = self.get_active_page()
        except Exception:
            pass
            
        return BrowserInteractionHelper.execute_interaction(
            page=page,
            query=selector_or_query,
            action_type=action_type,
            action_fn=action_fn,
            max_retries=max_retries,
            initial_delay=0.5
        )
        
    def _attach_page_listeners(self, page: Page) -> None:
        """Attaches console log and request failed event listeners to page."""
        if getattr(page, "_diagnostics_attached", None) is True:
            return
            
        page._diagnostics_attached = True
        page._console_logs = []
        page._network_errors = []
        
        def on_console(msg):
            log_entry = f"[{msg.type}] {msg.text}"
            if msg.location:
                log_entry += f" ({msg.location.get('url')}:{msg.location.get('lineNumber')})"
            page._console_logs.append(log_entry)
            if len(page._console_logs) > 500:
                page._console_logs.pop(0)
                
        def on_request_failed(req):
            failure = req.failure
            err = failure.error_text if failure else "Unknown failure"
            page._network_errors.append(f"Failed request: {req.method} {req.url} - {err}")
            if len(page._network_errors) > 200:
                page._network_errors.pop(0)
                
        def on_popup(popup_page):
            try:
                self._attach_page_listeners(popup_page)
                self.set_active_page(popup_page)
                from nova.logger import logger
                logger.info(f"Browser Automation detected popup window: {popup_page.url}")
            except Exception:
                pass
                
        try:
            page.on("console", on_console)
            page.on("requestfailed", on_request_failed)
            page.on("popup", on_popup)
        except Exception:
            pass

    def capture_diagnostics(self, exception: Exception) -> Dict[str, str]:
        """Captures screenshot, page source, console logs, and request failures on error."""
        diag_info = {}
        try:
            page = self.get_active_page(silent=True)
        except Exception:
            return diag_info
            
        timestamp = int(time.time())
        profile_dir = os.path.expanduser("~/.config/nova-chromium-profile")
        diag_dir = os.path.join(profile_dir, "diagnostics")
        
        try:
            os.makedirs(diag_dir, exist_ok=True)
        except Exception:
            diag_dir = "/tmp"
            
        screenshot_path = os.path.join(diag_dir, f"screenshot_{timestamp}.png")
        html_path = os.path.join(diag_dir, f"source_{timestamp}.html")
        report_path = os.path.join(diag_dir, f"report_{timestamp}.json")
        
        try:
            page.screenshot(path=screenshot_path, timeout=5000)
            diag_info["screenshot"] = screenshot_path
        except Exception as e:
            diag_info["screenshot_error"] = f"Failed to capture screenshot: {e}"
            
        try:
            html = page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            diag_info["html"] = html_path
        except Exception as e:
            diag_info["html_error"] = f"Failed to capture HTML: {e}"
            
        report = {
            "timestamp": timestamp,
            "url": page.url,
            "exception": str(exception),
            "traceback": traceback.format_exc(),
            "console_logs": getattr(page, "_console_logs", []),
            "network_errors": getattr(page, "_network_errors", [])
        }
        
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            diag_info["report"] = report_path
        except Exception as e:
            diag_info["report_error"] = f"Failed to save report: {e}"
            
        from nova.logger import logger
        logger.error(
            f"Nova Browser Automation Failure Diagnostics:\n"
            f"  - URL: {report['url']}\n"
            f"  - Screenshot: {screenshot_path}\n"
            f"  - HTML Source: {html_path}\n"
            f"  - Full Report: {report_path}"
        )
        
        return diag_info

    def detect_login(self, page: Page) -> bool:
        """Detects if the page displays login / auth buttons."""
        try:
            for term in ("Log in", "Sign in", "Login", "Sign Up", "Register"):
                loc = self._detector.detect_element(page, term, "click")
                if loc.first.is_visible(timeout=1000):
                    return False
        except Exception:
            pass
        return True

    def get_browser_instance(self) -> Browser:
        """Helper to safely retrieve the Playwright browser instance."""
        from nova.browser_manager import BrowserManager
        return BrowserManager.get_browser()
        
    def get_active_context(self) -> BrowserContext:
        """Retrieves currently active context, fallback to default persistent context."""
        if self._active_context:
            try:
                _ = self._active_context.pages
                return self._active_context
            except Exception:
                self._active_context = None
                
        browser = self.get_browser_instance()
        from nova.browser_manager import BrowserManager
        ctx = BrowserManager.get_persistent_context(browser)
        self._active_context = ctx
        return ctx
        
    def set_active_context(self, context: BrowserContext) -> None:
        self._active_context = context
        self._active_page = None
        
    def clear_active_context_cache(self) -> None:
        self._active_context = None
        self._active_page = None
        
    def get_active_page(self, silent: bool = False) -> Page:
        """Finds active page inside active context using priority rules."""
        if self._active_page:
            try:
                _ = self._active_page.url
                return self._active_page
            except Exception:
                self._active_page = None
                
        context = self.get_active_context()
        pages = context.pages
        target_page = None
        
        for p in pages:
            try:
                if p.evaluate("document.visibilityState === 'visible'"):
                    target_page = p
                    break
            except Exception:
                pass
                
        if not target_page:
            for p in pages:
                try:
                    if p.evaluate("document.hasFocus()"):
                        target_page = p
                        break
                except Exception:
                    pass
                    
        if not target_page:
            if pages:
                target_page = pages[0]
            else:
                target_page = context.new_page()
                
        self._active_page = target_page
        
        if not silent:
            from nova.browser_manager import BrowserManager
            BrowserManager.focus_browser(target_page)
            
        return target_page
        
    def set_active_page(self, page: Page) -> None:
        self._active_page = page
        
    def clear_active_page_cache(self) -> None:
        self._active_page = None
        
    def execute_action(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Looks up the operation action class and executes it."""
        op_key = str(operation).strip().lower()
        from nova.logger import logger
        
        logger.info(f"Nova Automation Step Start - Operation: {operation}, Parameters: {params}")
        start_time = time.time()
        
        action = self._actions.get(op_key)
        if not action:
            err_msg = f"Unsupported browser automation operation: '{operation}'"
            logger.error(f"Nova Automation Step Error - {err_msg}")
            return {
                "status": "error",
                "message": err_msg
            }
            
        try:
            self.get_browser_instance()
            
            ctx = self.get_active_context()
            if not getattr(ctx, "_listeners_attached", False):
                try:
                    ctx.on("page", lambda p: self._attach_page_listeners(p))
                    ctx._listeners_attached = True
                except Exception:
                    pass
            for p in ctx.pages:
                self._attach_page_listeners(p)
                
            result = action.execute(self, params)
            elapsed = time.time() - start_time
            
            if result.get("status") == "success":
                logger.info(f"Nova Automation Step Success - Operation: {operation} (took {elapsed:.2f}s). Result: {result.get('message')}")
            else:
                logger.error(f"Nova Automation Step Failure - Operation: {operation} (took {elapsed:.2f}s). Error: {result.get('message')}")
                diag = self.capture_diagnostics(Exception(result.get("message")))
                result["diagnostics"] = diag
                
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            err_msg = str(e).lower()
            if any(kw in err_msg for kw in ("closed", "disconnected", "target closed", "connection lost", "crashed")):
                try:
                    self.recover_browser()
                except Exception:
                    pass
            logger.error(f"Nova Automation Step Exception - Operation: {operation} (took {elapsed:.2f}s). Exception: {e}")
            diag = self.capture_diagnostics(e)
            return {
                "status": "error",
                "message": f"Unexpected error executing action '{operation}': {e}",
                "diagnostics": diag
            }
