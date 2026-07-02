import time
try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False


def test_fill():
    if not _PLAYWRIGHT_AVAILABLE:
        print("Playwright is not available!")
        return
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        
        chatgpt_page = None
        for page in context.pages:
            if "chatgpt.com" in page.url.lower():
                chatgpt_page = page
                break
                
        if not chatgpt_page:
            print("ChatGPT page not found!")
            return
            
        print("Found ChatGPT page. Attempting to fill div#prompt-textarea...")
        
        # Focus and click first
        chatgpt_page.focus("div#prompt-textarea")
        chatgpt_page.click("div#prompt-textarea")
        
        # Clear if there's any text
        # type the query
        chatgpt_page.type("div#prompt-textarea", "What is the meaning of hello?")
        print("Typed query. Pressing Enter...")
        chatgpt_page.keyboard.press("Enter")
        
        print("Submitted. Waiting 5 seconds to verify...")
        time.sleep(5)
        print("Done.")

if __name__ == "__main__":
    test_fill()
