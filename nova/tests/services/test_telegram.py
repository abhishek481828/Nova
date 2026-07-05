import unittest
from unittest.mock import MagicMock, patch
import os

from nova.services.telegram import TelegramService

class TestTelegramService(unittest.TestCase):
    def setUp(self):
        # Set up a test instance
        self.service = TelegramService()
        self.service.chat_id = 98765  # Force mock chat ID

    @patch("httpx.Client")
    def test_unlock_passcode_flow(self, mock_client_class):
        # Patch the environment variables during the test execution
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "12345:token",
            "TELEGRAM_CHAT_ID": "98765",
            "TELEGRAM_UNLOCK_PASSWORD": "mypassword"
        }):
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            
            # Mock getUpdates return values:
            # 1. First poll: unlock laptop request
            # 2. Second poll: incorrect password
            # 3. Third poll: another unlock request
            # 4. Fourth poll: correct password
            # 5. Fifth: KeyboardInterrupt to terminate loop
            mock_client.get.side_effect = [
                MagicMock(status_code=200, json=lambda: {
                    "result": [{
                        "update_id": 100,
                        "message": {
                            "chat": {"id": 98765},
                            "text": "unlock laptop"
                        }
                    }]
                }),
                MagicMock(status_code=200, json=lambda: {
                    "result": [{
                        "update_id": 101,
                        "message": {
                            "chat": {"id": 98765},
                            "text": "wrongpass"
                        }
                    }]
                }),
                MagicMock(status_code=200, json=lambda: {
                    "result": [{
                        "update_id": 102,
                        "message": {
                            "chat": {"id": 98765},
                            "text": "unlock laptop"
                        }
                    }]
                }),
                MagicMock(status_code=200, json=lambda: {
                    "result": [{
                        "update_id": 103,
                        "message": {
                            "chat": {"id": 98765},
                            "text": "mypassword"
                        }
                    }]
                }),
                # Stop the loop with a KeyboardInterrupt
                KeyboardInterrupt()
            ]

            # Mock send_message and _execute_command
            self.service.send_message = MagicMock(return_value=True)
            self.service._execute_command = MagicMock(return_value="Desktop screen unlocked successfully.")

            # Run polling loop (it will raise KeyboardInterrupt to terminate)
            try:
                self.service._polling_loop(MagicMock(), {})
            except KeyboardInterrupt:
                pass

            # Verify sent messages:
            # 1. Startup message: "Nova is online..."
            # 2. Prompt for password: "🔒 Please enter the unlock password:"
            # 3. Incorrect password reply: "❌ Incorrect password..."
            # 4. Prompt for password again: "🔒 Please enter the unlock password:"
            # 5. Success reply: "✅ Password correct..."
            sent_texts = [call[0][0] for call in self.service.send_message.call_args_list]
            self.assertIn("🔒 Please enter the unlock password:", sent_texts)
            self.assertIn("❌ Incorrect password. Unlock request denied.", sent_texts)
            self.assertIn("✅ Password correct. Desktop screen unlocked successfully.", sent_texts)
            
            # Verify unlock command was executed
            self.service._execute_command.assert_called_with("unlock screen", unittest.mock.ANY, unittest.mock.ANY, speak_on_laptop=unittest.mock.ANY)

    @patch("nova.voice.pipeline.get_current_state")
    @patch("nova.voice.pipeline.transition_state")
    @patch("nova.voice.pipeline.voice_active_event")
    def test_remote_voice_control(self, mock_event, mock_transition, mock_get_state):
        from nova.voice.pipeline import VoiceState
        
        # Test 1: Start voice mode when inactive
        mock_get_state.return_value = VoiceState.INACTIVE
        res = self.service._execute_command("voice command on", MagicMock(), {})
        self.assertIn("activated on your laptop", res)
        mock_transition.assert_called_with(VoiceState.VOICE_IDLE)
        mock_event.set.assert_called_once()
        
        # Test 2: Deactivate voice mode
        mock_transition.reset_mock()
        res = self.service._execute_command("voice command off", MagicMock(), {})
        self.assertIn("deactivated on your laptop", res)
        mock_transition.assert_called_with(VoiceState.INACTIVE)

    @patch("httpx.Client")
    @patch("subprocess.run")
    @patch("pathlib.Path.write_bytes")
    @patch("pathlib.Path.read_bytes")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.mkdir")
    @patch("nova.voice.whisper.get_stt_provider")
    def test_transcribe_telegram_voice(self, mock_get_stt, mock_mkdir, mock_unlink, mock_exists, mock_read_bytes, mock_write_bytes, mock_run, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Mock API calls: getFile and file download
        mock_client.get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"result": {"file_path": "voice_dir/voice.oga"}}),
            MagicMock(status_code=200, content=b"fake ogg data")
        ]
        
        # Mock subprocess execution of ffmpeg (returncode = 0)
        mock_run.return_value = MagicMock(returncode=0)
        mock_exists.return_value = True # File exists check for output WAV
        
        # Mock STT provider
        mock_stt = MagicMock()
        mock_stt.transcribe.return_value = "how is the weather"
        mock_get_stt.return_value = mock_stt
        
        res = self.service._transcribe_telegram_voice("voice_file_id_123")
        self.assertEqual(res, "how is the weather")
        mock_stt.transcribe.assert_called_once()

    @patch("httpx.Client")
    @patch("subprocess.run")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.mkdir")
    @patch("nova.voice.tts.EdgeTTSProvider._synthesize")
    def test_send_voice_message(self, mock_synthesize, mock_mkdir, mock_unlink, mock_exists, mock_run, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(status_code=200)
        
        mock_synthesize.return_value = "/tmp/test.mp3"
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0) # ffmpeg success
        
        with patch("builtins.open", unittest.mock.mock_open(read_data=b"oggdata")):
            res = self.service.send_voice_message("test output")
            self.assertTrue(res)
            mock_client.post.assert_called_once()

    @patch("nova.core.memory.HistoryManager.load_history")
    @patch("nova.voice.tts.speak")
    def test_remote_speak_more_and_stop(self, mock_speak, mock_load_history):
        import nova.voice.config as voice_config
        
        # Test 1: Stop speaking (various shapes)
        for stop_cmd in ("stop nova", "stop.", "stop!", "stop, nova.", "stop speaking"):
            voice_config.interrupt_speaking = False
            res = self.service._execute_command(stop_cmd, MagicMock(), {})
            self.assertIn("Speech output stopped", res)
            self.assertTrue(voice_config.interrupt_speaking)
        
        # Test 2: Speak more when no history exists
        mock_load_history.return_value = []
        res = self.service._execute_command("speak more", MagicMock(), {})
        self.assertIn("No previous task execution", res)
        
        # Test 3: Speak more with valid history
        mock_load_history.return_value = [
            {
                "user_input": "show system status",
                "result_message": "battery level is 97 percent",
                "timestamp": "2026-07-05T12:00:00"
            }
        ]
        # Mock LLM API response or let fallback catch it
        res = self.service._execute_command("speak more", MagicMock(), {})
        self.assertIn("Speaking more details", res)
        mock_speak.assert_called_once()

if __name__ == "__main__":
    unittest.main()
