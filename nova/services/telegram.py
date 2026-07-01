import os
import time
import httpx
import threading
import re
from nova.logger import logger
from nova.utils import print_info, print_error

class TelegramService:
    def __init__(self):
        self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

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
                            sender_chat_id = chat.get("id")

                            if not text or sender_chat_id is None:
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

                            # Execute the command
                            logger.info(f"Telegram remote command received: '{text}'")
                            response_text = self._execute_command(text, ai_client, dispatcher)
                            
                            # Send response back
                            self.send_message(response_text)
            except Exception as e:
                # Log error and wait a few seconds before retrying
                logger.error(f"Error in Telegram polling loop: {e}")
                time.sleep(5)

            # Prevent high CPU consumption if updates return instantly
            time.sleep(1)

    def _execute_command(self, query: str, ai_client, dispatcher) -> str:
        """Helper to run commands, capture terminal prints, and return final output."""
        if query.lower() == "/start":
            return (
                "Hello! I am Nova, your AI assistant.\n\n"
                "You can control your PC remotely from here. Just type any request like:\n"
                "• what's the weather?\n"
                "• lock my screen\n"
                "• is firefox running?\n"
                "• list my github repositories"
            )

        from nova.utils import set_capture_callback
        from nova.spelling import correct_query_spelling, correct_action_data
        from nova.parser import parse_and_validate_action
        from nova.core.memory import HistoryManager
        from nova.core.executor import CommandExecutor

        captured_output = []
        def capture_cb(msg):
            # Strip ANSI escape sequences
            clean = re.sub(r'\x1b\[[0-9;]*m', '', msg)
            captured_output.append(clean)
            
        set_capture_callback(capture_cb)
        
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
            
        return "".join(captured_output).strip() or "Command completed with no output."
