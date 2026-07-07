import sys
import os
import unittest
try:
    import numpy as np
    from nova.voice.pipeline import process_single_iteration, VoiceLoopState, VoiceState, transition_state
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False

from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from nova.core.memory import WorkingMemory, Interaction, reset_working_memory


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestVoiceMemoryIntegration(unittest.TestCase):

    def setUp(self):
        # Reset the process-wide shared memory to guarantee test isolation
        reset_working_memory()

        self.patcher = patch("nova.core.state.StateManager.is_autonomous", return_value=True)
        self.mock_is_autonomous = self.patcher.start()


        # Mock BrowserManager to bypass browser check in tests
        self.browser_patcher = patch("nova.browser.manager.BrowserManager")
        self.mock_browser_manager = self.browser_patcher.start()
        self.mock_browser_manager.is_browser_running.return_value = True
        self.mock_browser = MagicMock()
        self.mock_browser_manager.get_browser.return_value = self.mock_browser
        self.mock_context = MagicMock()
        self.mock_browser_manager.get_persistent_context.return_value = self.mock_context
        self.mock_page = MagicMock()
        self.mock_page.url = "https://youtube.com"
        self.mock_context.pages = [self.mock_page]

        # Patch find_active_page
        self.find_page_patcher = patch("nova.browser.helper.find_active_page", return_value=self.mock_page)
        self.mock_find_active_page = self.find_page_patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.browser_patcher.stop()
        self.find_page_patcher.stop()

    @patch("nova.voice.pipeline.get_stt_provider")
    @patch("nova.voice.pipeline.LocalWakeWordDetector")
    @patch("nova.voice.pipeline.SpeakerVerifier")
    @patch("nova.voice.pipeline.AmbientCalibrator")
    @patch("nova.voice.pipeline.HighPassFilter")
    @patch("nova.voice.pipeline.RNNoiseWrapper")
    @patch("nova.voice.pipeline.AecProcessor")
    @patch("nova.voice.pipeline.WebRTCVoiceActivityDetector")
    @patch("nova.voice.pipeline.speak")
    @patch("nova.voice.pipeline.play_confirmation_sound")
    @patch("nova.voice.pipeline._wait_for_wake")
    @patch("nova.voice.pipeline.sd")
    @patch("nova.voice.pipeline.record_audio_from_stream")
    @patch("nova.voice.pipeline.AudioQualityAnalyzer")
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
        mock_handler = MagicMock()
        mock_handler.execute.return_value = "YouTube opened successfully"
        mock_handler.is_long_running = False  # Avoid MagicMock's truthy hasattr check
        mock_dispatcher = {
            "open_browser": mock_handler,
            "close_browser": mock_handler,
            "greeting": mock_handler
        }

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

    @patch("nova.voice.pipeline.get_stt_provider")
    @patch("nova.voice.pipeline.LocalWakeWordDetector")
    @patch("nova.voice.pipeline.SpeakerVerifier")
    @patch("nova.voice.pipeline.AmbientCalibrator")
    @patch("nova.voice.pipeline.HighPassFilter")
    @patch("nova.voice.pipeline.RNNoiseWrapper")
    @patch("nova.voice.pipeline.AecProcessor")
    @patch("nova.voice.pipeline.WebRTCVoiceActivityDetector")
    @patch("nova.voice.pipeline.speak")
    @patch("nova.voice.pipeline.play_confirmation_sound")
    @patch("nova.voice.pipeline._wait_for_wake")
    @patch("nova.voice.pipeline.sd")
    @patch("nova.voice.pipeline.record_audio_from_stream")
    @patch("nova.voice.pipeline.AudioQualityAnalyzer")
    def test_voice_pipeline_properties_and_exception_safety(
        self, mock_qa_class, mock_record_stream, mock_sd, mock_wait_for_wake,
        mock_play_sound, mock_speak, mock_vad, mock_aec, mock_rnnoise,
        mock_hp, mock_calibrator, mock_speaker_verifier, mock_wake_detector_class,
        mock_get_stt
    ):
        """Verify that voice properties are stored on trigger events, and memory failures are handled gracefully."""
        # 1. Setup states and mock variables
        transition_state(VoiceState.VOICE_IDLE)
        
        mock_stt_inst = MagicMock()
        mock_stt_inst.transcribe.return_value = "hello assistant"
        mock_stt_inst.last_avg_logprob = 0.0
        mock_get_stt.return_value = mock_stt_inst

        mock_sd.query_devices.return_value = {"name": "Mock Mic"}
        mock_sd.InputStream.return_value = MagicMock()
        
        mock_ai_client = MagicMock()
        mock_ai_client.parse_intent.return_value = "MOCK_JSON_ACTIONS"
        mock_ai_client.generate_tts_summary.return_value = "Hello."

        # Mock action dispatcher
        mock_handler = MagicMock()
        mock_handler.execute.return_value = "Executed"
        mock_handler.is_long_running = False
        mock_dispatcher = {
            "open_browser": mock_handler,
            "close_browser": mock_handler,
            "greeting": mock_handler
        }

        mock_calib_inst = MagicMock()
        mock_calib_inst.noise_floor = 0.001
        mock_calib_inst.speech_threshold = 0.002
        mock_calibrator.return_value = mock_calib_inst

        mock_detector_inst = MagicMock()
        mock_detector_inst.model_name = "hey_nova"
        mock_wake_detector_class.return_value = mock_detector_inst

        mock_wait_for_wake.return_value = (True, np.zeros(4800, dtype=np.float32), 0.95)

        mock_verifier_inst = MagicMock()
        mock_verifier_inst._threshold = 0.75
        mock_verifier_inst.verify.return_value = (True, 0.9)
        mock_speaker_verifier.return_value = mock_verifier_inst

        mock_record_stream.return_value = b"dummy audio"

        mock_qa = MagicMock()
        mock_qa.analyze.return_value = {
            "overall_quality": 0.9,
            "background_noise": 0.01
        }
        mock_qa_class.return_value = mock_qa

        def test_transition_to(new_state, detail=""):
            state.current_state = new_state
            transition_state(new_state)

        # Inject WorkingMemory
        wm = WorkingMemory()
        state = VoiceLoopState(working_memory=wm)
        state.current_state = VoiceState.VOICE_IDLE
        state.verifier = mock_verifier_inst

        with patch("nova.parser.parse_and_validate_action", return_value=[{"action": "greeting"}]):
            # Verify turn properties
            action = process_single_iteration(state, mock_ai_client, mock_dispatcher, test_transition_to)
            self.assertEqual(action, "continue")
            
            # Assert all voice properties were populated in working memory
            self.assertTrue(wm.get("wake_word_activation"))
            self.assertEqual(wm.get("listening_state"), "listening")
            self.assertGreater(wm.get("recognition_confidence"), 0.0)
            self.assertEqual(wm.get("current_speaker"), "verified")
            self.assertEqual(wm.get("final_transcription"), "hello assistant")

        # 2. Test Exception Safety (WorkingMemory set method raises an error)
        # Verify that process_single_iteration does not crash when memory updates throw exceptions
        with patch.object(wm, "set", side_effect=ValueError("Working memory backend unavailable")):
            with patch("nova.parser.parse_and_validate_action", return_value=[{"action": "greeting"}]):
                action2 = process_single_iteration(state, mock_ai_client, mock_dispatcher, test_transition_to)
                self.assertEqual(action2, "continue")  # Ran successfully without crashing!

    @patch("nova.voice.pipeline.get_stt_provider")
    @patch("nova.voice.pipeline.LocalWakeWordDetector")
    @patch("nova.voice.pipeline.SpeakerVerifier")
    @patch("nova.voice.pipeline.AmbientCalibrator")
    @patch("nova.voice.pipeline.HighPassFilter")
    @patch("nova.voice.pipeline.RNNoiseWrapper")
    @patch("nova.voice.pipeline.AecProcessor")
    @patch("nova.voice.pipeline.WebRTCVoiceActivityDetector")
    @patch("nova.voice.pipeline.speak")
    @patch("nova.voice.pipeline.play_confirmation_sound")
    @patch("nova.voice.pipeline._wait_for_wake")
    @patch("nova.voice.pipeline.sd")
    def test_voice_session_state_lifecycle(
        self, mock_sd, mock_wait_for_wake, mock_play_sound, mock_speak,
        mock_vad, mock_aec, mock_rnnoise, mock_hp, mock_calibrator,
        mock_speaker_verifier, mock_wake_detector_class, mock_get_stt
    ):
        """Verify that voice_session_state updates to active and inactive during the loop lifecycle."""
        from nova.voice.pipeline import run_voice_loop
        import threading
        
        mock_get_stt.return_value = MagicMock()
        mock_sd.query_devices.return_value = {"name": "Mock Mic"}
        mock_sd.InputStream.return_value = MagicMock()
        mock_ai_client = MagicMock()
        mock_dispatcher = {}

        local_shutdown = threading.Event()
        
        # Shutdown after 1 iteration to test session transitions
        def wait_side_effect(*args, **kwargs):
            local_shutdown.set()
            return False, None, 0.0
        mock_wait_for_wake.side_effect = wait_side_effect

        wm = WorkingMemory()
        
        with patch("nova.voice.pipeline.shutdown_event", local_shutdown), \
             patch("time.sleep", return_value=None), \
             patch("nova.voice.pipeline.AudioQualityAnalyzer") as mock_qa_class:
            
            mock_qa = MagicMock()
            mock_qa_class.return_value = mock_qa

            # Execute voice loop
            run_voice_loop(mock_ai_client, mock_dispatcher, interactive=True, working_memory=wm)

            # After exit, voice_session_state should transition back to inactive
            self.assertEqual(wm.get("voice_session_state"), "inactive")

if __name__ == "__main__":
    unittest.main()
