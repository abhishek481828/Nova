import os
import time
import httpx
import threading
import re
from nova.logger import logger
from nova.utils import print_info, print_error
from nova.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class TelegramService:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self._chat_states = {}

    def _load_password_from_env_file(self) -> str:
        try:
            from pathlib import Path
            env_path = Path("/home/nixos/Projects/Nova/.env")
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.strip().startswith("TELEGRAM_UNLOCK_PASSWORD="):
                        val = line.split("=", 1)[1].strip()
                        if val.startswith(('"', "'")) and val.endswith(('"', "'")):
                            val = val[1:-1]
                        return val
        except Exception:
            pass
        return ""

    def send_message(self, text: str) -> bool:
        """Sends a text message to the configured Telegram chat."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram Bot Token or Chat ID is not configured.")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text
        }
        
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def start_polling(self, ai_client, dispatcher) -> None:
        """Starts a background thread to poll for commands from Telegram."""
        if not self.bot_token or not self.chat_id:
            logger.info("Telegram Bot Token or Chat ID is missing. Polling thread disabled.")
            return

        t = threading.Thread(
            target=self._polling_loop,
            args=(ai_client, dispatcher),
            daemon=True,
            name="telegram_polling_thread"
        )
        t.start()
        print_info("Telegram remote command listener started.")

    def _polling_loop(self, ai_client, dispatcher) -> None:
        offset = 0
        url = f"{self.base_url}/getUpdates"
        
        # Send a startup notification to the owner
        self.send_message("Nova is online and listening for remote commands!")

        while True:
            params = {
                "offset": offset,
                "timeout": 30
            }
            try:
                with httpx.Client(timeout=35.0) as client:
                    resp = client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        updates = data.get("result", [])
                        for update in updates:
                            update_id = update.get("update_id", 0)
                            offset = update_id + 1
                            
                            message = update.get("message", {})
                            chat = message.get("chat", {})
                            from_user = message.get("from", {})
                            text = message.get("text", "").strip()
                            voice = message.get("voice")
                            sender_chat_id = chat.get("id")

                            if sender_chat_id is None:
                                continue

                            is_voice_query = False
                            # Download and transcribe voice notes if present
                            if voice and not text:
                                file_id = voice.get("file_id")
                                text = self._transcribe_telegram_voice(file_id)
                                if text:
                                    is_voice_query = True

                            if not text:
                                continue

                            # Security Verification: Only execute commands from the authorized user
                            if str(sender_chat_id) != str(self.chat_id):
                                logger.warning(f"Unauthorized access attempt from Chat ID: {sender_chat_id} (User: {from_user.get('username')})")
                                unauthorized_url = f"{self.base_url}/sendMessage"
                                client.post(unauthorized_url, json={
                                    "chat_id": sender_chat_id,
                                    "text": "Unauthorized user. Remote control of this Nova instance is restricted."
                                })
                                continue

                            # Check chat state
                            chat_state = self._chat_states.get(sender_chat_id)
                            if chat_state and chat_state.get("state") == "WAITING_PASSWORD":
                                # Handle password verification
                                password = os.environ.get("TELEGRAM_UNLOCK_PASSWORD")
                                if not password:
                                    password = self._load_password_from_env_file()
                                
                                if not password:
                                    self._chat_states.pop(sender_chat_id, None)
                                    self.send_message("⚠️ Unlock password is not configured in .env. Request aborted.")
                                    continue
                                    
                                if text.strip().lower() == password.strip().lower():
                                    self._chat_states.pop(sender_chat_id, None)
                                    logger.info(f"Telegram remote unlock authorized by correct password.")
                                    response_text = self._execute_command("unlock screen", ai_client, dispatcher, speak_on_laptop=is_voice_query)
                                    self.send_message(f"✅ Password correct. {response_text}")
                                else:
                                    self._chat_states.pop(sender_chat_id, None)
                                    self.send_message("❌ Incorrect password. Unlock request denied.")
                                continue

                            # Check if the query is an unlock request
                            # Match: "unlock", "unlock laptop", "unlock screen", "unlock my laptop" etc.
                            query_lower = text.lower().strip()
                            _is_unlock = (
                                query_lower == "unlock"
                                or query_lower.startswith("unlock ")
                                or query_lower.startswith("unlock my ")
                            )
                            if _is_unlock:
                                password = os.environ.get("TELEGRAM_UNLOCK_PASSWORD")
                                if not password:
                                    password = self._load_password_from_env_file()
                                    
                                if not password:
                                    self.send_message("⚠️ Unlock password is not set. Please define TELEGRAM_UNLOCK_PASSWORD in your .env file to enable remote unlock.")
                                    continue
                                
                                self._chat_states[sender_chat_id] = {
                                    "state": "WAITING_PASSWORD",
                                    "pending_command": "unlock"
                                }
                                self.send_message("🔒 Please enter the unlock password:")
                                continue

                            # Execute the command
                            logger.info(f"Telegram remote command received: '{text}' (Voice query: {is_voice_query})")
                            response_text = self._execute_command(text, ai_client, dispatcher, speak_on_laptop=is_voice_query)
                            
                            # Send response back
                            self.send_message(response_text)
            except Exception as e:
                # Log error and wait a few seconds before retrying
                logger.error(f"Error in Telegram polling loop: {e}")
                time.sleep(5)

            # Prevent high CPU consumption if updates return instantly
            time.sleep(1)

    def _execute_command(self, query: str, ai_client, dispatcher, speak_on_laptop: bool = False) -> str:
        """Helper to run commands, capture terminal prints, and return final output."""
        if query.lower() == "/start":
            return (
                "👋 Hello! I am Nova, your AI laptop assistant.\n\n"
                "You can control your PC remotely:\n"
                "• *any question* → ask anything\n"
                "• `lock screen` → lock your laptop screen\n"
                "• `unlock laptop` → unlock screen (asks for password)\n"
                "• `suspend laptop` → put laptop to sleep\n"
                "• `system status` → battery, CPU, RAM info\n"
                "• `what's the weather?` → current weather\n"
                "• `lock my screen` → lock screen\n\n"
                "⚠️ *Wake from suspend*: When your laptop is suspended,\n"
                "Nova cannot receive messages (CPU is asleep).\n"
                "Use a Wake-on-LAN app on your phone to wake it first,\n"
                f"then the screen auto-unlocks.\n"
                f"Your laptop WiFi MAC: `48:68:4a:70:83:de`"
            )

        query_clean = query.strip().lower()
        if query_clean in (
            "activate voice mode", "start voice mode", "turn on voice mode",
            "voice mode on", "voice command on", "voice on", "turn on voice", "start voice"
        ):
            from nova.voice.pipeline import get_current_state, VoiceState, voice_active_event, transition_state
            state = get_current_state()
            if state in (VoiceState.VOICE_IDLE, VoiceState.TEXT_MODE, VoiceState.INACTIVE):
                transition_state(VoiceState.VOICE_IDLE)
                voice_active_event.set()
                return "Nova voice mode has been activated on your laptop. It is now listening via the microphone."
            else:
                return f"Nova voice mode is already active (State: {state.name})."
                
        elif query_clean in (
            "deactivate voice mode", "stop voice mode", "turn off voice mode",
            "voice mode off", "voice command off", "voice off", "turn off voice", "stop voice"
        ):
            from nova.voice.pipeline import get_current_state, VoiceState, transition_state
            transition_state(VoiceState.INACTIVE)
            return "Nova voice mode has been deactivated on your laptop. It is no longer listening."

        # Check for direct speech interrupt commands via Telegram (e.g. "stop nova", "stop speaking")
        query_stripped = query_clean.rstrip(".!? ")
        if (
            query_stripped in ("stop", "stop speaking", "stop nova", "shut up", "pause speaking", "quiet", "be quiet")
            or query_stripped.startswith(("stop ", "stop, "))
        ):
            import nova.voice.config as voice_config
            voice_config.interrupt_speaking = True
            logger.info("Remote speaking interrupt triggered from Telegram.")
            return "Speech output stopped on laptop speakers."

        # Check for detailed explanation request
        if query_clean in (
            "speak more about this task", "speak more about the task", "speak more",
            "tell me more", "explain more", "give me more details"
        ):
            from nova.core.memory import HistoryManager
            from nova.voice.tts import speak
            history = HistoryManager.load_history()
            
            # Find the most recent entry with a result_message (ignoring the current query)
            prev_entry = None
            for entry in reversed(history):
                # Skip history entries for 'speak more' / 'stop speaking' etc.
                user_in = entry.get("user_input", "").lower().strip()
                if any(kw in user_in for kw in ("speak more", "tell me more", "explain more", "give me more", "stop nova", "stop speaking")):
                    continue
                if entry.get("result_message"):
                    prev_entry = entry
                    break
                    
            if not prev_entry:
                return "No previous task execution was found in history to explain."
                
            prev_user_input = prev_entry.get("user_input")
            prev_result_message = prev_entry.get("result_message")
            
            # Ask the LLM to generate a detailed summary
            prompt = (
                "You are Nova, an AI assistant. The user wants you to explain in detail about the last completed task.\n"
                f"The last task request was: '{prev_user_input}'\n"
                f"The execution result was:\n{prev_result_message}\n\n"
                "Write a natural, detailed spoken explanation describing the execution details, results, or data. "
                "Adhere to these rules:\n"
                "1. Keep it under 60 words.\n"
                "2. Make it clear, fluent, conversational, and optimized for text-to-speech.\n"
                "3. NEVER include markdown, tables, bullets, code blocks, URLs, file paths, JSON, logs, or stack traces.\n"
                "4. Output ONLY the raw spoken text. Do not wrap in quotes."
            )
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Explain in detail about the completed task."}
            ]
            
            # Call LLM
            from nova.config import GEMINI_API_KEY, NEBIUS_API_KEY
            from nova.services.nebius import call_nebius_llm
            import httpx
            
            content = ""
            if NEBIUS_API_KEY:
                content = call_nebius_llm(messages=messages, temperature=0.0)
            elif GEMINI_API_KEY:
                try:
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
                    combined_text = messages[0].get("content", "") + "\n\n" + messages[1].get("content", "")
                    gemini_payload = {
                        "contents": [{"role": "user", "parts": [{"text": combined_text}]}],
                        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 100}
                    }
                    with httpx.Client() as client:
                        gemini_resp = client.post(gemini_url, json=gemini_payload, timeout=8.0)
                        if gemini_resp.status_code == 200:
                            content = gemini_resp.json().get("candidates", [])[0].get("content", {}).get("parts", [])[0].get("text", "").strip()
                except Exception:
                    pass
                    
            if not content:
                # Rule-based fallback summary
                content = f"The previous task was {prev_user_input}. The result was: {prev_result_message[:100]}"
                
            content = content.strip().strip('"').strip("'").strip('`').strip()
            
            logger.info(f"Laptop speaking detailed response: '{content}'")
            speak(content)
            
            return f"Speaking more details: {content}"

        from nova.utils import set_capture_callback
        from nova.spelling import correct_query_spelling, correct_action_data
        from nova.parser import parse_and_validate_action
        from nova.core.memory import HistoryManager
        from nova.core.executor import CommandExecutor

        captured_output = []
        def capture_cb(msg):
            import re
            # Strip ANSI escape sequences
            clean = re.sub(r'\x1b\[[0-9;]*m', '', msg)
            captured_output.append(clean)
            
        set_capture_callback(capture_cb)
        
        last_result_message = ""
        try:
            query = correct_query_spelling(query)
            query_lower = query.lower().strip()
            
            if query_lower in ("history", "show history", "view history", "list history"):
                HistoryManager.print_history()
                return "".join(captured_output).strip() or "No history found."
                
            # Parse intent
            raw_response = ai_client.parse_intent(query)
            if not raw_response:
                return "Failed to parse query intent."
                
            actions_list = parse_and_validate_action(raw_response)
            if not actions_list:
                return f"Could not determine or parse action from AI response: {raw_response}"
                
            for action_data in actions_list:
                action_data = correct_action_data(action_data, query)
                action_name = action_data.get("action")
                action_handler = dispatcher.get(action_name)
                
                if not action_handler:
                    return f"No handler registered for action '{action_name}'."
                    
                result_message = action_handler.execute(action_data)
                last_result_message = result_message
                # Print result so that capture_callback registers it
                from nova.utils import print_success, print_error
                if "error" in result_message.lower() or "failed" in result_message.lower():
                    print_error(result_message)
                else:
                    print_success(result_message)
                    
        except Exception as e:
            return f"Error executing command: {e}"
        finally:
            set_capture_callback(None)
            
        response_text = "".join(captured_output).strip() or "Command completed with no output."
        if speak_on_laptop:
            try:
                from nova.voice.tts import speak
                import re

                speak_text = last_result_message or response_text
                
                # Clean up markdown formatting (bold, links, code tags) for clean text-to-speech
                clean_speech = speak_text
                clean_speech = re.sub(r'\*\*|__', '', clean_speech)  # Bold
                clean_speech = re.sub(r'\*|_', '', clean_speech)    # Italics
                clean_speech = re.sub(r'`', '', clean_speech)       # Inline code
                clean_speech = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', clean_speech)  # Markdown links
                clean_speech = re.sub(r'#+\s+', '', clean_speech)   # Headers
                clean_speech = clean_speech.strip()

                # Check if it contains a table, code block, or is too long for direct speech
                has_tables_or_code = "|" in clean_speech or "```" in clean_speech
                word_count = len(clean_speech.split())

                if has_tables_or_code or word_count > 120:
                    logger.info("Response is complex or too long; generating TTS summary...")
                    clean_speech = ai_client.generate_tts_summary(query, speak_text)

                logger.info(f"Laptop speaking: '{clean_speech}'")
                speak(clean_speech)
            except Exception as speak_err:
                logger.error(f"Error speaking response on laptop: {speak_err}")
            
        return response_text

    def _transcribe_telegram_voice(self, file_id: str) -> str:
        """Downloads a Telegram voice message, converts it to WAV, and transcribes it."""
        try:
            import httpx
            import subprocess
            from pathlib import Path
            from nova.voice.whisper import get_stt_provider

            # 1. Fetch file info from Telegram
            file_info_url = f"{self.base_url}/getFile"
            with httpx.Client(timeout=15.0) as client:
                file_info_resp = client.get(file_info_url, params={"file_id": file_id})
                if file_info_resp.status_code != 200:
                    logger.error(f"Failed to get voice file info from Telegram: {file_info_resp.text}")
                    return ""
                
                file_info = file_info_resp.json().get("result", {})
                file_path = file_info.get("file_path")
                if not file_path:
                    logger.error("No file_path returned in Telegram getFile response.")
                    return ""

                # 2. Download the voice file (typically .ogg or .oga)
                download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
                download_resp = client.get(download_url)
                if download_resp.status_code != 200:
                    logger.error(f"Failed to download voice file from Telegram: {download_resp.text}")
                    return ""
                
                voice_bytes = download_resp.content

            # 3. Save to scratch space inside the workspace
            scratch_dir = Path("/home/nixos/Projects/Nova/scratch")
            scratch_dir.mkdir(parents=True, exist_ok=True)
            oga_path = scratch_dir / "telegram_voice.oga"
            wav_path = scratch_dir / "telegram_voice.wav"

            if oga_path.exists():
                oga_path.unlink()
            if wav_path.exists():
                wav_path.unlink()

            oga_path.write_bytes(voice_bytes)

            # 4. Convert .oga to WAV via ffmpeg
            res = subprocess.run([
                "ffmpeg", "-y", "-i", str(oga_path),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)
            ], capture_output=True, text=True)

            if res.returncode != 0:
                logger.error(f"ffmpeg conversion failed: {res.stderr}")
                return ""

            if not wav_path.exists():
                logger.error("WAV file was not generated by ffmpeg.")
                return ""

            # 5. Transcribe using Nova's STT provider
            wav_bytes = wav_path.read_bytes()
            stt_provider = get_stt_provider()
            transcription = stt_provider.transcribe(wav_bytes, silent=True)
            return transcription.strip()

        except Exception as e:
            logger.error(f"Error in _transcribe_telegram_voice: {e}")
            return ""

    def send_voice_message(self, text: str) -> bool:
        """Synthesizes text, converts it to OGG, and sends it to Telegram."""
        if not self.bot_token or not self.chat_id:
            return False
            
        import tempfile
        import subprocess
        from pathlib import Path
        import httpx
        from nova.voice.tts import EdgeTTSProvider

        mp3_path = None
        ogg_path = None
        try:
            logger.info(f"Synthesizing voice reply text ({len(text)} chars)...")
            # 1. Synthesize text to MP3 using EdgeTTS
            provider = EdgeTTSProvider()
            mp3_path = provider._synthesize(text)
            if not mp3_path or not Path(mp3_path).exists():
                logger.error("EdgeTTS synthesis returned None or output file does not exist.")
                return False

            logger.info(f"TTS Synthesized successfully. Converting to OGG: {mp3_path}")
            # 2. Setup output OGG path
            scratch_dir = Path("/home/nixos/Projects/Nova/scratch")
            scratch_dir.mkdir(parents=True, exist_ok=True)
            ogg_path = str(scratch_dir / "telegram_response.ogg")

            if Path(ogg_path).exists():
                Path(ogg_path).unlink()

            # 3. Convert MP3 to OGG Opus via ffmpeg
            res = subprocess.run([
                "ffmpeg", "-y", "-i", mp3_path,
                "-c:a", "libopus", "-b:a", "32k", ogg_path
            ], capture_output=True)

            if res.returncode != 0 or not Path(ogg_path).exists():
                logger.error(f"Failed to convert TTS to OGG: {res.stderr.decode('utf-8', errors='ignore')}")
                return False

            logger.info(f"OGG conversion successful: {ogg_path}. Uploading voice message to Telegram...")
            # 4. Send to Telegram sendVoice
            url = f"{self.base_url}/sendVoice"
            payload = {"chat_id": self.chat_id}
            
            with open(ogg_path, "rb") as voice_file:
                files = {
                    "voice": ("voice.ogg", voice_file, "audio/ogg")
                }
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(url, data=payload, files=files)
                    resp.raise_for_status()
                    logger.info("Voice message uploaded and sent successfully.")
                    return True

        except Exception as e:
            logger.error(f"Error in send_voice_message: {e}")
            return False
        finally:
            # Clean up temp files
            if mp3_path and Path(mp3_path).exists():
                try:
                    Path(mp3_path).unlink()
                except Exception:
                    pass
            if ogg_path and Path(ogg_path).exists():
                try:
                    Path(ogg_path).unlink()
                except Exception:
                    pass
