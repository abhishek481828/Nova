import json
from playwright.sync_api import sync_playwright

def inspect():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        
        chatgpt_page = None
        for page in context.pages:
            if "chatgpt.com" in page.url.lower() or "openai.com" in page.url.lower():
                chatgpt_page = page
                break
                
        if not chatgpt_page:
            print("ChatGPT page not found!")
            return
            
        print(f"Page Title: {chatgpt_page.title()}")
        print(f"Page URL: {chatgpt_page.url}")
        
        # Find all textarea, input, and contenteditable elements
        elements = chatgpt_page.locator("textarea, input, [contenteditable='true']").all()
        print(f"Found {len(elements)} input-like elements:")
        for i, el in enumerate(elements):
            try:
                tag = el.evaluate("el => el.tagName")
                el_id = el.evaluate("el => el.id")
                name = el.evaluate("el => el.name")
                placeholder = el.evaluate("el => el.placeholder")
                classes = el.evaluate("el => el.className")
                visible = el.is_visible()
                print(f"[{i}] Tag: {tag}, ID: {el_id}, Name: {name}, Placeholder: {placeholder}, Classes: {classes}, Visible: {visible}")
            except Exception as e:
                print(f"[{i}] Error: {e}")

if __name__ == "__main__":
    inspect()
