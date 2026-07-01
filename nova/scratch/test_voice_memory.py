import sys
import os
import unittest
import numpy as np
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from nova.voice.conversation import process_single_iteration, VoiceLoopState, VoiceState, transition_state
from nova.working_memory import WorkingMemory, Interaction

class TestVoiceMemoryIntegration(unittest.TestCase):

    @patch("nova.voice.conversation.get_stt_provider")
    @patch("nova.voice.conversation.LocalWakeWordDetector")
    @patch("nova.voice.conversation.SpeakerVerifier")
    @patch("nova.voice.audio_processor.AmbientCalibrator")
    @patch("nova.voice.audio_processor.HighPassFilter")
    @patch("nova.voice.audio_processor.RNNoiseWrapper")
    @patch("nova.voice.audio_processor.AecProcessor")
    @patch("nova.voice.audio_processor.WebRTCVoiceActivityDetector")
    @patch("nova.voice.conversation.speak")
    @patch("nova.voice.conversation.play_confirmation_sound")
    @patch("nova.voice.conversation._wait_for_wake")
    @patch("nova.voice.conversation.sd")
    @patch("nova.voice.conversation.record_audio_from_stream")
    @patch("nova.voice.conversation.AudioQualityAnalyzer")
    def test_working_memory_turn_updates(
        self, mock_qa_class, mock_record_stream, mock_sd, mock_wait_for_wake,
        mock_play_sound, mock_speak, mock_vad, mock_aec, mock_rnnoise,
        mock_hp, mock_calibrator, mock_speaker_verifier, mock_wake_detector_class,
        mock_get_stt
    ):
        """Verify that conversation turns update the injected Working Memory automatically."""
        # 1. Setup states and mock variables
        transition_state(VoiceState.VOICE_IDLE)
        
        mock_stt_inst = MagicMock()
        mock_stt_inst.transcribe.return_value = "open youtube"
        mock_stt_inst.last_avg_logprob = 0.0  # Avoid mock comparison errors
        mock_get_stt.return_value = mock_stt_inst

        mock_sd.query_devices.return_value = {"name": "Mock Mic"}
        mock_sd.InputStream.return_value = MagicMock()
        
        # Mock AI Client parsing intent
        mock_ai_client = MagicMock()
        mock_ai_client.parse_intent.return_value = "MOCK_JSON_ACTIONS"
        mock_ai_client.generate_tts_summary.return_value = "Opening YouTube for you."

        # Mock action dispatcher
        mock_dispatcher = MagicMock()
        mock_handler = MagicMock()
        mock_handler.execute.return_value = "YouTube opened successfully"
        mock_handler.is_long_running = False  # Avoid MagicMock's truthy hasattr check
        mock_dispatcher.get.return_value = mock_handler

        mock_calib_inst = MagicMock()
        mock_calib_inst.noise_floor = 0.001
        mock_calib_inst.speech_threshold = 0.002
        mock_calibrator.return_value = mock_calib_inst

        mock_detector_inst = MagicMock()
        mock_detector_inst.model_name = "hey_nova"
        mock_wake_detector_class.return_value = mock_detector_inst

        mock_wait_for_wake.return_value = (True, np.zeros(4800, dtype=np.float32), 0.95)

        mock_verifier_inst = MagicMock()
        mock_verifier_inst.verify.return_value = (True, 0.9)
        mock_speaker_verifier.return_value = mock_verifier_inst

        mock_record_stream.return_value = b"dummy audio"

        mock_qa = MagicMock()
        mock_qa.analyze.return_value = {
            "overall_quality": 0.9,
            "background_noise": 0.01
        }
        mock_qa_class.return_value = mock_qa

        # Setup custom transition
        def test_transition_to(new_state, detail=""):
            state.current_state = new_state
            transition_state(new_state)

        # Inject WorkingMemory
        wm = WorkingMemory()
        state = VoiceLoopState(working_memory=wm)
        state.current_state = VoiceState.VOICE_IDLE
        state.verifier = mock_verifier_inst

        # Patch parsing intent parser function to return mocked structured action dict
        with patch("nova.parser.parse_and_validate_action", return_value=[{"action": "open_browser", "url": "https://youtube.com"}]):
            # Run first iteration
            action = process_single_iteration(state, mock_ai_client, mock_dispatcher, test_transition_to)
            self.assertEqual(action, "continue")
            
            # Assert working memory was populated
            self.assertEqual(wm.get("previous_command"), "open youtube")
            self.assertEqual(wm.get("previous_assistant_reply"), "Opening YouTube for you.")
            self.assertEqual(wm.get("current_intent"), "open_browser")
            self.assertEqual(wm.get("current_topic"), "open_browser: https://youtube.com")
            self.assertIsNone(wm.get("previous_intent"))
            self.assertIsNone(wm.get("previous_topic"))
            
            # Check conversation histories
            self.assertEqual(len(wm.state.conversation_history), 1)
            self.assertEqual(wm.state.conversation_history[0].user_prompt, "open youtube")
            self.assertEqual(len(wm.state.session_state.current_conversation), 1)

            # Modify mock STT transcription for turn 2 to test previous/current transitions
            mock_stt_inst.transcribe.return_value = "close chrome"
            
        with patch("nova.parser.parse_and_validate_action", return_value=[{"action": "close_browser"}]):
            mock_ai_client.generate_tts_summary.return_value = "Closing Chrome."
            mock_handler.execute.return_value = "Chrome closed successfully"
            
            # Run second iteration
            action2 = process_single_iteration(state, mock_ai_client, mock_dispatcher, test_transition_to)
            self.assertEqual(action2, "continue")

            # Assert working memory updated and transitioned previous states
            self.assertEqual(wm.get("previous_command"), "close chrome")
            self.assertEqual(wm.get("previous_assistant_reply"), "Closing Chrome.")
            self.assertEqual(wm.get("current_intent"), "close_browser")
            self.assertEqual(wm.get("current_topic"), "close_browser")
            
            # Verify previous values contain the first turn's intents/topics!
            self.assertEqual(wm.get("previous_intent"), "open_browser")
            self.assertEqual(wm.get("previous_topic"), "open_browser: https://youtube.com")

            # Check conversation histories grew to size 2 (no replacements, no duplicates)
            self.assertEqual(len(wm.state.conversation_history), 2)
            self.assertEqual(wm.state.conversation_history[1].user_prompt, "close chrome")
            self.assertEqual(len(wm.state.session_state.current_conversation), 2)

if __name__ == "__main__":
    unittest.main()
