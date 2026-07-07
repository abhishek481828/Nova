import os
import json
import httpx
from typing import Optional
from nova.config import OLLAMA_API_URL, OLLAMA_MODEL, SYSTEM_PROMPT, DISABLE_OLLAMA, NEBIUS_API_KEY, GEMINI_API_KEY
from nova.logger import log_error, log_request
from nova.services.nebius import call_nebius_llm

class OllamaClient:
    def __init__(self, api_url: str = OLLAMA_API_URL, model: str = OLLAMA_MODEL) -> None:
        self.api_url = api_url.rstrip("/")
        self.model = model

    def parse_intent(self, user_input: str) -> Optional[str]:
        """
        Sends the user request to Ollama with conversation history and returns the raw JSON string response.
        """
        log_request(user_input)
        url = f"{self.api_url}/api/chat"
        
        # Load recent history to provide context/memory
        from nova.core.memory import HistoryManager
        history_entries = HistoryManager.load_history()
        
        # Load user profile from StateManager
        from nova.core.state import StateManager
        user_profile = StateManager.get_user_profile()
        profile_context = ""
        if user_profile:
            profile_context = f"\n\nUser Profile (Known facts about the user):\n{json.dumps(user_profile, indent=2)}"
            
        # Build the messages list starting with system prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT + profile_context}]
        
        # Filter active history entries to keep payload size reasonable and maintain context
        active_entries = [
            e for e in history_entries[-2:]
            if e.get("parsed_action") and e.get("status") not in ("ollama_failed", "parse_failed")
        ]
        
        # Build alternating messages
        for i, entry in enumerate(active_entries):
            parsed_action = entry.get("parsed_action")
            user_msg = entry.get("user_input")
            
            if i == 0:
                messages.append({"role": "user", "content": user_msg})
            else:
                # Prepend the previous entry's execution result as context
                prev_entry = active_entries[i - 1]
                result = prev_entry.get("result_message") or ""
                if result:
                    content = f"Previous execution result: {result}\n\nUser request: {user_msg}"
                else:
                    content = user_msg
                messages.append({"role": "user", "content": content})
                
            messages.append({"role": "assistant", "content": json.dumps(parsed_action)})
            
        # Add the current user input, prepending the last history entry's execution result if available
        if active_entries:
            last_entry = active_entries[-1]
            result = last_entry.get("result_message") or ""
            if result:
                current_content = f"Previous execution result: {result}\n\nUser request: {user_input}"
            else:
                current_content = user_input
        else:
            current_content = user_input
            
        messages.append({"role": "user", "content": current_content})

        # --- Nebius AI Cloud Check ---
        nebius_key = NEBIUS_API_KEY
        if nebius_key:
            content = call_nebius_llm(
                messages=messages,
                temperature=0.0
            )
            if content:
                return content

        # --- Gemini API Fallback ---
        gemini_key = GEMINI_API_KEY
        if gemini_key:
            try:
                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                # Convert messages to Gemini format
                gemini_contents = []
                system_text = ""
                for msg in messages:
                    role = msg.get("role", "user")
                    text = msg.get("content", "")
                    if role == "system":
                        system_text = text
                    elif role == "user":
                        if system_text:
                            text = system_text + "\n\n" + text
                            system_text = ""
                        gemini_contents.append({"role": "user", "parts": [{"text": text}]})
                    elif role == "assistant":
                        gemini_contents.append({"role": "model", "parts": [{"text": text}]})
                if not gemini_contents:
                    gemini_contents = [{"role": "user", "parts": [{"text": system_text}]}]
                gemini_payload = {
                    "contents": gemini_contents,
                    "generationConfig": {"temperature": 0.0}
                }
                with httpx.Client() as client:
                    gemini_resp = client.post(
                        gemini_url,
                        json=gemini_payload,
                        timeout=15.0
                    )
                    if gemini_resp.status_code == 200:
                        resp_data = gemini_resp.json()
                        candidates = resp_data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                content = parts[0].get("text", "")
                                if content:
                                    return content
            except Exception as e:
                log_error("Gemini API call failed, falling back to local Ollama", e)

        # Fallback to local Ollama if not explicitly disabled (Critical fix)
        if DISABLE_OLLAMA:
            return None


        # --- Local Ollama execution ---
        # Prepare the chat request payload
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,  # We want deterministic JSON parsing
                "num_predict": 100   # Limit max generated tokens on CPU
            }
        }
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload,
                    timeout=60.0
                )
                if response.status_code != 200:
                    log_error(f"Ollama API returned non-200 status code: {response.status_code}")
                    return None
                
                resp_data = response.json()
                message = resp_data.get("message", {})
                content = message.get("content", "")
                return content
                
        except httpx.RequestError as e:
            log_error("Failed to connect to Ollama. Is it running? Try: systemctl start ollama", e)
            return None
        except Exception as e:
            log_error("An unexpected error occurred while calling Ollama", e)
            return None

    def generate_tts_summary(self, user_query: str, full_response: str) -> str:
        """
        Generates a concise spoken summary (1-2 sentences, usually < 20 words)
        of the completed task for TTS, adhering strictly to the spoken summary rules.
        """
        import re
        import os
        
        def clean_ansi(text: str) -> str:
            return re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)

        from nova.config import load_prompt
        fallback_prompt = (
            "You are a text-to-speech summary generator for the virtual assistant Nova.\n"
            "Given the user's request and the execution result, write a short, 1-2 sentence spoken summary of the result.\n"
            "Spoken Summary Rules:\n"
            "1. Must be under 20 words.\n"
            "2. State only what was completed, not how it was done (e.g. say 'Done. YouTube is open.' instead of 'Launched Chromium browser and connected to youtube.com').\n"
            "3. Sound natural and conversational, as if spoken by a voice assistant.\n"
            "4. NEVER include markdown, bullets, code blocks, URLs, file paths, JSON, logs, or stack traces.\n"
            "5. Never repeat information or include filler.\n"
            "6. Never claim success if the task failed. Do NOT start with 'Done' or 'Completed' for failures. Briefly state the failure reason.\n"
            "7. Output ONLY the raw spoken text. Do not wrap in quotes. Do not include introductory text like 'Here is your summary:'."
        )
        system_prompt = load_prompt("tts_summary_prompt.txt", fallback_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User Request: {user_query}\nExecution Result: {full_response}"}
        ]

        content = ""
        nebius_key = NEBIUS_API_KEY
        if nebius_key:
            nebius_content = call_nebius_llm(
                messages=messages,
                temperature=0.0,
                timeout=8.0
            )
            if nebius_content:
                content = nebius_content

        # Fallback to local Ollama if not explicitly disabled (Critical fix)
        if DISABLE_OLLAMA:
            pass

        # --- Gemini TTS Summary Fallback ---
        elif not content:
            gemini_key = GEMINI_API_KEY
            if gemini_key:
                try:
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                    combined_text = messages[0].get("content", "") + "\n\n" + messages[1].get("content", "")
                    gemini_payload = {
                        "contents": [{"role": "user", "parts": [{"text": combined_text}]}],
                        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 60}
                    }
                    with httpx.Client() as client:
                        gemini_resp = client.post(
                            gemini_url,
                            json=gemini_payload,
                            timeout=8.0
                        )
                        if gemini_resp.status_code == 200:
                            resp_data = gemini_resp.json()
                            candidates = resp_data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    content = parts[0].get("text", "").strip()
                except Exception as e:
                    log_error("Gemini summary generation failed, falling back to local Ollama", e)

        # Local Ollama fallback if neither Nebius nor Gemini succeeded
        if not DISABLE_OLLAMA and not content:
            url = f"{self.api_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 40
                }
            }
            try:
                with httpx.Client() as client:
                    response = client.post(
                        url,
                        json=payload,
                        timeout=12.0
                    )
                    if response.status_code == 200:
                        resp_data = response.json()
                        content = resp_data.get("message", {}).get("content", "").strip()
            except Exception as e:
                log_error("Ollama summary generation failed", e)

        # Post-process and clean generated content
        if content:
            content = clean_ansi(content).strip()
            
            # If the model wrapped the response in quotes (e.g. '"Done."') or added a preamble, extract quotes
            quoted_match = re.search(r'"([^"]+)"', content)
            if quoted_match and any(keyword in content.lower() for keyword in ["here is", "spoken", "summary", "result"]):
                content = quoted_match.group(1)
            
            # Remove any wrapping quotes or backticks
            content = content.strip().strip('"').strip("'").strip('`').strip()
            if content:
                return content

        # Rule-based clean fallback
        clean_text = clean_ansi(full_response).strip()
        clean_text = re.sub(r'```[\s\S]*?```', '', clean_text)
        clean_text = re.sub(r'`.*?`', '', clean_text)
        clean_text = re.sub(r'\[.*?\]\(.*?\)', '', clean_text)
        clean_text = re.sub(r'https?://\S+', '', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text)
        
        words = clean_text.split()
        if len(words) <= 15:
            return clean_text

        if "error" in clean_text.lower() or "failed" in clean_text.lower():
            return "I couldn't complete that task."
        return "Done. The task is complete."

    def generate_chatgpt_tts_summary(self, user_query: str, response: str) -> str:
        """
        Generates a concise conversational summary (1-3 sentences, usually under 60 words)
        of a long ChatGPT response for natural voice output.
        """
        import re
        import os
        
        def clean_ansi(text: str) -> str:
            return re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)

        system_prompt = (
            "You are a text-to-speech summary generator for the virtual assistant Nova.\n"
            "Given the user's question and ChatGPT's detailed response, summarize the answer "
            "into a concise, conversational 1-3 sentence response (under 60 words) suitable for reading aloud.\n"
            "Do NOT include markdown, HTML, code snippets, lists, or special characters. Output ONLY the raw summary text."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Question: {user_query}\nDetailed Response: {response}"}
        ]

        content = ""
        nebius_key = NEBIUS_API_KEY
        if nebius_key:
            nebius_content = call_nebius_llm(
                messages=messages,
                temperature=0.3,
                timeout=8.0
            )
            if nebius_content:
                content = nebius_content

        # Fallback to local Ollama if not explicitly disabled
        if not DISABLE_OLLAMA and not content:
            url = f"{self.api_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 100
                }
            }
            try:
                with httpx.Client() as client:
                    resp = client.post(
                        url,
                        json=payload,
                        timeout=12.0
                    )
                    if resp.status_code == 200:
                        content = resp.json().get("message", {}).get("content", "").strip()
            except Exception:
                pass

        if content:
            content = clean_ansi(content).strip()
            content = content.strip().strip('"').strip("'").strip('`').strip()
            if content:
                return content

        # Simple fallback: return the first 3 sentences of the response
        clean_text = clean_ansi(response).strip()
        clean_text = re.sub(r'```[\s\S]*?```', '', clean_text)
        clean_text = re.sub(r'`.*?`', '', clean_text)
        clean_text = re.sub(r'\[.*?\]\(.*?\)', '', clean_text)
        clean_text = re.sub(r'https?://\S+', '', clean_text)
        
        sentences = re.split(r'(?<=[.!?])\s+', clean_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if sentences:
            return " ".join(sentences[:3])
        return "Here is the response from ChatGPT."

    def enhance_prompt(self, prompt: str) -> str:
        """
        Enhances the user's raw prompt using the prompt enhancer system prompt.
        """
        import re
        from nova.config import load_prompt
        
        def clean_ansi(text: str) -> str:
            return re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)

        fallback_prompt = (
            "You are a Prompt Enhancer for the Nova Virtual Assistant. Your goal is to improve and expand the user's spoken request into a high-quality, detailed, and context-rich prompt suitable for ChatGPT, while strictly preserving the user's original intention.\n"
            "Follow these strict rules:\n"
            "1. Do not lose key facts, names, technologies, or parameters from the original request.\n"
            "2. Expand the prompt to request detailed explanations, clear code structure, and comments if code is requested.\n"
            "3. Keep the prompt professional, clear, and direct.\n"
            "4. Output ONLY the enhanced prompt itself. Never include introduction, backticks, conversational filler, or quotes."
        )
        system_prompt = load_prompt("prompt_enhancer_prompt.txt", fallback_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        content = ""
        nebius_key = NEBIUS_API_KEY
        if nebius_key:
            nebius_content = call_nebius_llm(
                messages=messages,
                temperature=0.0,
                timeout=10.0
            )
            if nebius_content:
                content = nebius_content

        if not DISABLE_OLLAMA and not content:
            gemini_key = GEMINI_API_KEY
            if gemini_key:
                try:
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                    combined_text = messages[0].get("content", "") + "\n\n" + messages[1].get("content", "")
                    gemini_payload = {
                        "contents": [{"role": "user", "parts": [{"text": combined_text}]}],
                        "generationConfig": {"temperature": 0.0}
                    }
                    with httpx.Client() as client:
                        gemini_resp = client.post(
                            gemini_url,
                            json=gemini_payload,
                            timeout=10.0
                        )
                        if gemini_resp.status_code == 200:
                            resp_data = gemini_resp.json()
                            candidates = resp_data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    content = parts[0].get("text", "").strip()
                except Exception as e:
                    log_error("Gemini prompt enhancement failed, falling back to local Ollama", e)

        # Local Ollama fallback if neither Nebius nor Gemini succeeded
        if not DISABLE_OLLAMA and not content:
            url = f"{self.api_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 150
                }
            }
            try:
                with httpx.Client() as client:
                    response = client.post(
                        url,
                        json=payload,
                        timeout=15.0
                    )
                    if response.status_code == 200:
                        resp_data = response.json()
                        content = resp_data.get("message", {}).get("content", "").strip()
            except Exception as e:
                log_error("Ollama prompt enhancement failed", e)

        if content:
            content = clean_ansi(content).strip()
            # Clean wrapping quotes if the model output them
            content = content.strip().strip('"').strip("'").strip('`').strip()
            return content

        return prompt

    def translate_text(self, text: str, target_language: str) -> str:
        """Translates the given text into the target language using the LLM."""
        import os
        
        messages = [
            {
                "role": "system",
                "content": f"You are a translator. Translate the given text into {target_language}. Return ONLY the direct translation text. Do not explain, write preambles or wrap in quotes."
            },
            {"role": "user", "content": text}
        ]
        
        nebius_key = os.environ.get("NEBIUS_API_KEY") or NEBIUS_API_KEY
        if nebius_key:
            content = call_nebius_llm(messages=messages, temperature=0.0)
            if content:
                return content.strip()
                
        # Fallback to local Ollama
        if not DISABLE_OLLAMA:
            url = f"{self.api_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.0}
            }
            try:
                with httpx.Client() as client:
                    resp = client.post(url, json=payload, timeout=12.0)
                    if resp.status_code == 200:
                        return resp.json().get("message", {}).get("content", "").strip()
            except Exception:
                pass
                
        return f"[Translation to {target_language} failed. Original text]: {text}"

