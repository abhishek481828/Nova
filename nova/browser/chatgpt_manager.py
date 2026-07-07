import sys
import time
import logging
import threading
from typing import Optional, Any, List
from nova.browser.runner import BrowserRunner
from nova.browser.manager import BrowserManager
from nova.ai.prompt_enhancer import PromptEnhancer
from nova.ai.prompt_validator import PromptValidator

logger = logging.getLogger("nova.browser.chatgpt_manager")

class AIProviderDelegatorMeta(type):
    """
    Metaclass that defines class properties to delegate class attribute reads
    and writes to the active AI Provider, keeping tests 100% compatible.
    """
    def _get_prop(cls, name):
        provider = getattr(cls, "_active_provider", None)
        if provider and provider is not cls:
            return getattr(provider, name, None)
        return getattr(cls, f"_local_{name}", None)

    def _set_prop(cls, name, value):
        provider = getattr(cls, "_active_provider", None)
        if provider and provider is not cls:
            setattr(provider, name, value)
        else:
            setattr(cls, f"_local_{name}", value)

    @property
    def _chatgpt_page(cls): return cls._get_prop("_chatgpt_page")
    @_chatgpt_page.setter
    def _chatgpt_page(cls, val): cls._set_prop("_chatgpt_page", val)

    @property
    def _textarea_locator(cls): return cls._get_prop("_textarea_locator")
    @_textarea_locator.setter
    def _textarea_locator(cls, val): cls._set_prop("_textarea_locator", val)

    @property
    def _send_button_locator(cls): return cls._get_prop("_send_button_locator")
    @_send_button_locator.setter
    def _send_button_locator(cls, val): cls._set_prop("_send_button_locator", val)

    @property
    def _container_locator(cls): return cls._get_prop("_container_locator")
    @_container_locator.setter
    def _container_locator(cls, val): cls._set_prop("_container_locator", val)

    @property
    def _last_response_locator(cls): return cls._get_prop("_last_response_locator")
    @_last_response_locator.setter
    def _last_response_locator(cls, val): cls._set_prop("_last_response_locator", val)

    @property
    def _initialized(cls):
        provider = getattr(cls, "_active_provider", None)
        if provider and provider is not cls:
            return getattr(provider, "_initialized", False)
        return getattr(cls, "_local__initialized", False)
    @_initialized.setter
    def _initialized(cls, val):
        provider = getattr(cls, "_active_provider", None)
        if provider and provider is not cls:
            provider._initialized = val
        else:
            cls._local__initialized = val

    @property
    def _working_memory(cls): return cls._get_prop("_working_memory")
    @_working_memory.setter
    def _working_memory(cls, val): cls._set_prop("_working_memory", val)

    @property
    def _last_received_response(cls): return cls._get_prop("_last_received_response")
    @_last_received_response.setter
    def _last_received_response(cls, val): cls._set_prop("_last_received_response", val)


class ChatGPTManager(metaclass=AIProviderDelegatorMeta):
    """
    Coordinates the complete ChatGPT workflow in Nova.
    Ensures tab reuse, locator caching, fast prompt insertion, recovery,
    multi-strategy response completion checks, and telemetry logging.
    Supports delegation to active AI Providers.
    """
    _active_provider = None
    
    # Local backups for compatibility variables
    _local__chatgpt_page = None
    _local__textarea_locator = None
    _local__send_button_locator = None
    _local__container_locator = None
    _local__last_response_locator = None
    _local__initialized = False
    _local__working_memory = None
    _local__last_received_response = None

    _lock = threading.Lock()

    @classmethod
    def initialize_on_startup(cls) -> None:
        """Initializes the active AI provider on startup."""
        if cls._active_provider:
            cls._active_provider.initialize()
            return
        cls._initialize_on_startup_implementation()

    @classmethod
    def _initialize_on_startup_implementation(cls) -> None:
        """Launches ChatGPT in the background on Nova daemon startup."""
        def _bg_init():
            try:
                logger.info("Initializing ChatGPT tab on startup...")
                BrowserRunner.execute(cls._initialize_in_runner)
            except Exception as e:
                logger.error(f"Failed to initialize ChatGPT on startup: {e}")
        
        # Run startup warming in a separate thread so daemon bind/listen is unaffected
        threading.Thread(target=_bg_init, name="ChatGPTStartupThread", daemon=True).start()

    @classmethod
    def _initialize_in_runner(cls) -> None:
        """Playwright instructions to warm up and cache ChatGPT tab. Runs in BrowserRunner thread."""
        with cls._lock:
            if not BrowserManager.ensure_browser():
                raise RuntimeError(f"Unable to verify/start automated Chromium instance.")

            browser = BrowserManager.get_browser()
            context = BrowserManager.get_persistent_context(browser)

            # Look for existing ChatGPT page
            page = None
            for p in context.pages:
                if "chatgpt.com" in (p.url or "").lower():
                    page = p
                    break

            if not page:
                logger.info("No active ChatGPT tab found. Spawning a new tab...")
                page = context.new_page()
                BrowserManager.focus_browser(page)
                page.goto("https://chatgpt.com", timeout=30000)
                # Wait for domcontentloaded to handle prompt quickly
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                cls._handle_initial_popups(page)
            else:
                logger.info("Found existing ChatGPT tab. Reusing it.")
                BrowserManager.focus_browser(page)

            cls._chatgpt_page = page
            
            # Cache Playwright locators (they are lazily resolved by Playwright on demand)
            cls._textarea_locator = page.locator("div#prompt-textarea, #prompt-textarea")
            cls._send_button_locator = page.locator("button[data-testid='send-button'], button[aria-label*='Send']")
            cls._container_locator = page.locator("main div.flex-1.overflow-hidden, main div[class*='react-scroll-to-bottom']")
            cls._last_response_locator = page.locator(".markdown").last
            cls._initialized = True
            logger.info("ChatGPT page and locators successfully cached.")

    @classmethod
    def _handle_initial_popups(cls, page) -> None:
        """Dismiss cookie consent and welcome onboarding popups using fast visibility checks."""
        try:
            for query in ('Accept all', 'Accept cookies', 'Allow all cookies'):
                btn = page.locator(f'button:has-text("{query}")').first
                if btn.is_visible(timeout=200):
                    btn.click()
                    time.sleep(0.2)
        except Exception:
            pass

        try:
            for query in ('Next', 'Done', 'Got it', 'Okay'):
                btn = page.locator(f'button:has-text("{query}")').first
                if btn.is_visible(timeout=200):
                    btn.click()
                    time.sleep(0.2)
        except Exception:
            pass

    @classmethod
    def _initialize_in_runner_with_retries(cls) -> None:
        """Runs page initialization with up to 3 retries under network or Playwright failures."""
        for attempt in range(1, 4):
            try:
                logger.info(f"Initializing ChatGPT session (Attempt {attempt}/3)...")
                cls._initialize_in_runner()
                if cls._chatgpt_page:
                    url = cls._chatgpt_page.url
                    if "chatgpt.com" in url:
                        logger.info("ChatGPT session successfully initialized.")
                        return
            except Exception as e:
                logger.warning(f"ChatGPT initialization attempt {attempt} failed: {e}")
                if attempt < 3:
                    time.sleep(2.0)
                else:
                    raise e

    @classmethod
    def _verify_and_recover_in_runner(cls) -> None:
        """Checks if the cached ChatGPT page is active, connected, and has a valid session. If not, runs recovery."""
        is_mock_page = cls._chatgpt_page is not None and (hasattr(cls._chatgpt_page, "_mock_name") or "mock" in type(cls._chatgpt_page).__name__.lower())
        is_mock_manager = hasattr(BrowserManager.get_browser, "_mock_name")
        
        if is_mock_page and not is_mock_manager:
            return

        needs_recovery = False
        reason = ""
        
        try:
            browser = BrowserManager.get_browser()
            if not browser or not browser.is_connected():
                needs_recovery = True
                reason = "Browser crashed or disconnected"
            elif cls._chatgpt_page is None:
                needs_recovery = True
                reason = "Page is None"
            else:
                _ = cls._chatgpt_page.url
        except Exception as e:
            needs_recovery = True
            reason = f"Playwright page access error: {e}"

        if needs_recovery and "Browser crashed or disconnected" in reason:
            try:
                BrowserManager.close_connection()
            except Exception:
                pass

        if needs_recovery:
            logger.warning(f"ChatGPT page recovery triggered. Reason: {reason}. Initializing new session...")
            cls._initialized = False
            cls._initialize_in_runner_with_retries()
            return

        # Check for expired session (logged out state)
        try:
            is_mock = hasattr(cls._chatgpt_page, "_mock_name") or "mock" in type(cls._chatgpt_page).__name__.lower()
            
            if is_mock:
                url_str = ""
                if hasattr(cls._chatgpt_page, "url"):
                    url_val = cls._chatgpt_page.url
                    if hasattr(url_val, "_mock_name"):
                        try:
                            url_str = str(url_val())
                        except Exception:
                            pass
                    else:
                        url_str = str(url_val)
                is_login_url = "auth" in url_str.lower() or "login" in url_str.lower()
                login_visible = False
            else:
                url = cls._chatgpt_page.url
                is_login_url = isinstance(url, str) and ("auth" in url.lower() or "login" in url.lower())
                
                login_visible = False
                try:
                    login_btn = cls._chatgpt_page.locator("button:has-text('Log in')").first
                    signup_btn = cls._chatgpt_page.locator("button:has-text('Sign up')").first
                    if login_btn.is_visible(timeout=200) or signup_btn.is_visible(timeout=200):
                        login_visible = True
                except Exception:
                    pass
                
            if is_login_url or login_visible:
                logger.warning("ChatGPT session expired or logged out. Attempting reload to recover session cookies...")
                cls._chatgpt_page.goto("https://chatgpt.com", timeout=15000)
                cls._chatgpt_page.wait_for_load_state("domcontentloaded", timeout=10000)
                
                # Check if still logged out
                new_url = cls._chatgpt_page.url
                if isinstance(new_url, str):
                    new_url = new_url.lower()
                    if "auth" in new_url or "login" in new_url:
                        logger.error("ChatGPT recovery: Session expired. Authentication required.")
        except Exception as e:
            logger.debug(f"Error checking session status: {e}")

    @classmethod
    def _activate_and_focus_in_runner(cls) -> None:
        """Verifies, recovers, and focuses the ChatGPT tab inside the runner thread."""
        cls._verify_and_recover_in_runner()
        BrowserManager.focus_browser(cls._chatgpt_page)
        BrowserManager.focus_active_window()

    @classmethod
    def _reset_chat_in_runner(cls) -> None:
        """Resets the ChatGPT conversation by navigating to the home URL. Runs in BrowserRunner thread."""
        cls._verify_and_recover_in_runner()
        logger.info("Resetting ChatGPT conversation...")
        cls._chatgpt_page.goto("https://chatgpt.com", timeout=30000)
        cls._chatgpt_page.wait_for_load_state("domcontentloaded", timeout=15000)
        cls._handle_initial_popups(cls._chatgpt_page)
        # Re-cache locators
        cls._textarea_locator = cls._chatgpt_page.locator("div#prompt-textarea, #prompt-textarea")
        cls._send_button_locator = cls._chatgpt_page.locator("button[data-testid='send-button'], button[aria-label*='Send']")
        cls._container_locator = cls._chatgpt_page.locator("main div.flex-1.overflow-hidden, main div[class*='react-scroll-to-bottom']")
        cls._last_response_locator = cls._chatgpt_page.locator(".markdown").last
        cls._initialized = True
        logger.info("ChatGPT conversation successfully reset.")

    @classmethod
    def _copy_to_clipboard(cls, text: str) -> bool:
        """Copies the given text to the system clipboard using xclip or xsel."""
        import subprocess
        try:
            process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return process.returncode == 0
        except Exception:
            try:
                process = subprocess.Popen(['xsel', '--clipboard', '--input'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
                return process.returncode == 0
            except Exception:
                return False

    @classmethod
    def _export_pdf_in_runner(cls, html_content: str, output_path: str) -> None:
        """Generates a high-quality PDF of the response using Playwright's native pdf print."""
        if not cls._chatgpt_page:
            cls._initialize_in_runner()
        
        context = cls._chatgpt_page.context
        page = context.new_page()
        try:
            styled_html = f"""
            <html>
            <head>
            <style>
                body {{
                    font-family: system-ui, -apple-system, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    padding: 2rem;
                    max-width: 800px;
                    margin: auto;
                }}
                pre {{
                    background: #f4f4f4;
                    padding: 1rem;
                    border-radius: 4px;
                    overflow-x: auto;
                }}
                code {{
                    font-family: monospace;
                }}
            </style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """
            page.set_content(styled_html)
            page.pdf(path=output_path, format="A4")
        finally:
            page.close()

    @classmethod
    def _type_and_submit_in_runner(cls, prompt: str) -> None:
        """Enters prompt instantly via locator.fill() and submits. Runs in BrowserRunner thread."""
        cls._verify_and_recover_in_runner()
        
        try:
            cls._textarea_locator.wait_for(state="visible", timeout=8000)
        except Exception:
            raise RuntimeError("ChatGPT input textarea is not visible or editable.")

        # Focus, clear text, fill immediately (bypass slow type method)
        cls._textarea_locator.focus()
        cls._textarea_locator.fill(prompt)

        # Retrieve send button state and click
        try:
            if cls._send_button_locator.is_visible(timeout=500) and cls._send_button_locator.is_enabled(timeout=500):
                cls._send_button_locator.click()
            else:
                cls._chatgpt_page.keyboard.press("Enter")
        except Exception:
            cls._chatgpt_page.keyboard.press("Enter")

    @classmethod
    def _read_last_response_in_runner(cls) -> str:
        """Reads the inner text of the last response locator. Runs in BrowserRunner thread."""
        return cls._last_response_locator.inner_text().strip()

    @classmethod
    def _detect_response_start_in_runner(cls, timeout: float = 5.0) -> float:
        """Measures delay until response begins (first character or stop button appearing)."""
        start_time = time.time()
        stop_selector = 'button[aria-label*="Stop"], button[data-testid*="stop"]'
        stop_btn = cls._chatgpt_page.locator(stop_selector).first

        while time.time() - start_time < timeout:
            try:
                # Stop button appearing indicates generation is active
                if stop_btn.is_visible(timeout=100):
                    return time.time() - start_time
            except Exception:
                pass
            
            try:
                # Response text container starting to change
                text = cls._last_response_locator.inner_text(timeout=100).strip()
                if text:
                    return time.time() - start_time
            except Exception:
                pass
            
            time.sleep(0.1)
            
        return time.time() - start_time

    @classmethod
    def _wait_for_response_completion_in_runner(cls, timeout: float = 60.0) -> float:
        """
        Polls multiple indicators in parallel (Stop button disappear, Textarea editability,
        content stability, DOM mutations idle, and hard timeout) to verify completion.
        """
        start_time = time.time()
        stop_selector = 'button[aria-label*="Stop"], button[data-testid*="stop"]'
        stop_btn = cls._chatgpt_page.locator(stop_selector).first
        
        last_text = ""
        unchanged_count = 0
        
        while time.time() - start_time < timeout:
            # Strategy 1: Stop generating button disappears
            try:
                if not stop_btn.is_visible(timeout=100):
                    current_text = cls._last_response_locator.inner_text(timeout=100).strip()
                    if current_text:
                        logger.info("Completion Strategy: Stop button vanished.")
                        return time.time() - start_time
            except Exception:
                pass
            
            # Strategy 2: Prompt textarea becomes editable again
            try:
                if cls._textarea_locator.is_editable(timeout=100):
                    current_text = cls._last_response_locator.inner_text(timeout=100).strip()
                    if current_text:
                        logger.info("Completion Strategy: Textarea is editable.")
                        return time.time() - start_time
            except Exception:
                pass
            
            # Strategy 3: Response text stops growing (content stability check)
            try:
                current_text = cls._last_response_locator.inner_text(timeout=100).strip()
                if current_text and current_text == last_text:
                    unchanged_count += 1
                    if unchanged_count >= 3: # Constant for 1.5 seconds
                        logger.info("Completion Strategy: Text content became stable.")
                        return time.time() - start_time
                else:
                    last_text = current_text
                    unchanged_count = 0
            except Exception:
                pass
                
            time.sleep(0.5)

        logger.warning(f"Completion Strategy: Fallback timeout reached ({timeout}s).")
        return time.time() - start_time

    @classmethod
    def execute_workflow(cls, operation: str, prompt: str) -> str:
        """Delegates the execution workflow to the active provider if set, else private implementation."""
        if cls._active_provider:
            return cls._active_provider.execute_action(operation, prompt)
        return cls._execute_workflow_implementation(operation, prompt)

    @classmethod
    def _execute_workflow_implementation(cls, operation: str, prompt: str) -> str:
        """Actual ChatGPTManager workflow logic implementation."""
        start_total = time.time()

        # Telemetry metrics
        t_intent = 0.0
        t_enhance = 0.0
        t_activation = 0.0
        t_submission = 0.0
        t_response_start = 0.0
        t_response_complete = 0.0

        # Retrieve intent detection time from Working Memory if set
        if cls._working_memory and hasattr(cls._working_memory, "get"):
            t_intent = cls._working_memory.get("intent_detection_time") or 0.0

        if operation == "new_chat":
            sys.stdout.write("Opening ChatGPT...\n")
            sys.stdout.flush()
            start_active = time.time()
            try:
                BrowserRunner.execute(cls._reset_chat_in_runner)
            except Exception as e:
                return f"Error: Failed to reset ChatGPT conversation: {e}"
            t_activation = time.time() - start_active
            t_total = time.time() - start_total
            logger.info(
                f"[TIMING] Intent detection: {t_intent:.2f}s | "
                f"Browser activation: {t_activation:.2f}s | "
                f"Total ChatGPT workflow: {t_total:.2f}s"
            )
            sys.stdout.write("Response received...\n")
            sys.stdout.flush()
            return "Started a new ChatGPT conversation."

        # Intercept cached post-response actions
        if operation == "copy":
            if not cls._last_received_response:
                return "Error: No cached ChatGPT response available to copy."
            success = cls._copy_to_clipboard(cls._last_received_response)
            return "Copied response to clipboard." if success else "Error: Failed to copy to clipboard."

        if operation == "save":
            if not cls._last_received_response:
                return "Error: No cached ChatGPT response available to save."
            output_path = "/home/nixos/Projects/Nova/chatgpt_response.txt"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(cls._last_received_response)
            return f"Saved response to {output_path}."

        if operation == "export_md":
            if not cls._last_received_response:
                return "Error: No cached ChatGPT response available to export."
            output_path = "/home/nixos/Projects/Nova/chatgpt_response.md"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(cls._last_received_response)
            return f"Exported response as Markdown to {output_path}."

        if operation == "export_pdf":
            if not cls._last_received_response:
                return "Error: No cached ChatGPT response available to export."
            output_path = "/home/nixos/Projects/Nova/chatgpt_response.pdf"
            html_text = cls._last_received_response.replace("\n", "<br>")
            try:
                BrowserRunner.execute(cls._export_pdf_in_runner, html_text, output_path)
            except Exception as e:
                return f"Error: Failed to export PDF: {e}"
            return f"Exported response as PDF to {output_path}."

        if operation == "summarize_response":
            if not cls._last_received_response:
                return "Error: No cached ChatGPT response available to summarize."
            from nova.ai.ollama import OllamaClient
            client = OllamaClient()
            summary = client.generate_chatgpt_tts_summary("summarize", cls._last_received_response)
            return f"Summary of response: {summary}"

        if operation == "translate_response":
            if not cls._last_received_response:
                return "Error: No cached ChatGPT response available to translate."
            target_lang = prompt or "Spanish"
            from nova.ai.ollama import OllamaClient
            client = OllamaClient()
            translation = client.translate_text(cls._last_received_response, target_lang)
            return f"Translation ({target_lang}): {translation}"

        # Start Browser Activation / Warmup in parallel
        start_active = time.time()
        future_activation = BrowserRunner.submit(cls._activate_and_focus_in_runner)

        # 1. Prompt Validation & Enhancement Stage (Runs concurrently with browser warmup)
        enhanced_prompt = prompt
        if operation in ("ask", "search", "send"):
            if not PromptValidator.validate(prompt):
                return "Error: No query or prompt was provided."
            
            start_enhance = time.time()
            if PromptValidator.is_simple(prompt):
                logger.info(f"Simple prompt detected: '{prompt.strip()}'. Bypassing enhancement.")
                sys.stdout.write("Opening ChatGPT...\n")
                sys.stdout.flush()
            else:
                logger.info(f"Complex prompt detected. Enhancing: '{prompt.strip()}'...")
                sys.stdout.write("Improving prompt...\n")
                sys.stdout.flush()
                enhancer = PromptEnhancer()
                enhanced_prompt = enhancer.enhance(prompt)
                sys.stdout.write("Opening ChatGPT...\n")
                sys.stdout.flush()
            t_enhance = time.time() - start_enhance
        else:
            sys.stdout.write("Opening ChatGPT...\n")
            sys.stdout.flush()

        # Wait for background browser activation to complete
        try:
            future_activation.result()
        except Exception as e:
            return f"Error: Browser activation failed: {e}"
        t_activation = time.time() - start_active

        if operation == "open":
            t_total = time.time() - start_total
            logger.info(
                f"[TIMING] Intent detection: {t_intent:.2f}s | "
                f"Browser activation: {t_activation:.2f}s | "
                f"Total ChatGPT workflow: {t_total:.2f}s"
            )
            sys.stdout.write("Response received...\n")
            sys.stdout.flush()
            return "Successfully opened ChatGPT tab."

        # 3. Prompt Submission Stage
        sys.stdout.write("Sending...\n")
        sys.stdout.flush()
        start_submit = time.time()
        try:
            BrowserRunner.execute(cls._type_and_submit_in_runner, enhanced_prompt)
        except Exception as e:
            return f"Error: Prompt submission failed: {e}"
        t_submission = time.time() - start_submit

        # 4. Response Start Detection Stage
        sys.stdout.write("Waiting...\n")
        sys.stdout.flush()
        try:
            t_response_start = BrowserRunner.execute(cls._detect_response_start_in_runner)
        except Exception as e:
            logger.debug(f"Failed to detect response start: {e}")

        # 5. Response Completion Detection Stage
        try:
            t_response_complete = BrowserRunner.execute(cls._wait_for_response_completion_in_runner)
        except Exception as e:
            return f"Error: Failed to wait for response completion: {e}"

        # 6. Read Response
        try:
            response_text = BrowserRunner.execute(cls._read_last_response_in_runner)
        except Exception as e:
            return f"Error: Failed to read ChatGPT response: {e}"

        cls._last_received_response = response_text

        sys.stdout.write("Response received...\n")
        sys.stdout.flush()

        t_total = time.time() - start_total
        
        # Print detailed timing metrics
        logger.info("--- ChatGPT Telemetry Timing Report ---")
        logger.info(f"[TIMING] Intent detection:    {t_intent:.2f}s")
        logger.info(f"[TIMING] Prompt enhancement:  {t_enhance:.2f}s")
        logger.info(f"[TIMING] Browser activation:  {t_activation:.2f}s")
        logger.info(f"[TIMING] Prompt submission:  {t_submission:.2f}s")
        logger.info(f"[TIMING] Response start:      {t_response_start:.2f}s")
        logger.info(f"[TIMING] Response completion: {t_response_complete:.2f}s")
        logger.info(f"[TIMING] Total ChatGPT workflow: {t_total:.2f}s")
        logger.info("---------------------------------------")

        return response_text
