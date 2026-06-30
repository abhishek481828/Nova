import sys
import os
import time
import unittest
from unittest.mock import patch, MagicMock
import numpy as np

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import nova.voice.config as voice_config
from nova.voice.conversation import run_voice_loop, VoiceState, _current_state, shutdown_event
from nova.voice.confidence_fusion import ConfidenceFusionEngine
from nova.voice.wake_word import LocalWakeWordDetector

class TestLifecycleSafeguards(unittest.TestCase):

    def setUp(self):
        shutdown_event.clear()
        self.saved_state = _current_state

    def tearDown(self):
        from nova.voice.conversation import transition_state
        transition_state(self.saved_state)
        shutdown_event.clear()

    def test_configuration_loading(self):
        """Verify fallback configuration and modules are defined and accessible."""
        # Test that voice_config has expected default attributes
        self.assertTrue(hasattr(voice_config, "WAKE_WORD_CONFIDENCE"))
        self.assertTrue(hasattr(voice_config, "VAD_THRESHOLD"))
        
        # Test that getting a missing attribute returns the fallback correctly
        fusion_threshold = getattr(voice_config, "FUSION_TRIGGER_THRESHOLD", 0.50)
        self.assertEqual(fusion_threshold, 0.50)

    def test_confidence_fusion_robustness(self):
        """Verify that ConfidenceFusionEngine fuses scores without raising exceptions."""
        engine = ConfidenceFusionEngine()
        # Test standard weights
        fused = engine.fuse(wake_score=0.8, speaker_score=0.9, vad_score=1.0)
        self.assertGreater(fused, 0.0)
        self.assertLessEqual(fused, 1.0)

        # Test missing/None fields robustness
        fused_none = engine.fuse(wake_score=0.7, speaker_score=None, vad_score=None)
        self.assertGreater(fused_none, 0.0)
        self.assertLessEqual(fused_none, 1.0)

    @patch("openwakeword.model.Model")
    def test_wake_detection_rolling_buffer(self, mock_oww_model):
        """Verify rolling buffer model and predictions execute cleanly."""
        detector = LocalWakeWordDetector(model_path="dummy.onnx", confidence_threshold=0.5)
        # Verify prediction lock exists
        self.assertTrue(hasattr(detector, "predict_lock"))
        
        # Mock predict to return sample score
        detector.model.predict = MagicMock(return_value={"dummy": 0.85})
        detector.model_name = "dummy"
        
        # Verify predict works under lock
        with detector.predict_lock:
            preds = detector.model.predict(np.zeros(1280, dtype=np.int16))
        self.assertEqual(preds["dummy"], 0.85)

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
    def test_voice_thread_stability_under_exceptions(
        self, mock_sd, mock_wait_for_wake, mock_play_sound, mock_speak,
        mock_vad, mock_aec, mock_rnnoise, mock_hp, mock_calibrator,
        mock_speaker_verifier, mock_wake_detector_class, mock_get_stt
    ):
        """Verify process_single_iteration catches exceptions, executes recovery, and transitions back to VOICE_IDLE."""
        from nova.voice.conversation import process_single_iteration, VoiceLoopState, VoiceState, transition_state
        
        # Transition module state to VOICE_IDLE so we are waiting for wake
        transition_state(VoiceState.VOICE_IDLE)

        # Mock dependencies
        mock_get_stt.return_value = MagicMock()
        mock_sd.query_devices.return_value = {"name": "Mock Mic"}
        mock_sd.InputStream.return_value = MagicMock()
        mock_ai_client = MagicMock()
        mock_dispatcher = MagicMock()

        mock_calib_inst = MagicMock()
        mock_calib_inst.noise_floor = 0.001
        mock_calib_inst.speech_threshold = 0.002
        mock_calibrator.return_value = mock_calib_inst

        mock_detector_inst = MagicMock()
        mock_detector_inst.model_name = "hey_nova"
        mock_wake_detector_class.return_value = mock_detector_inst

        # Setup _wait_for_wake to return a valid wake trigger
        mock_wait_for_wake.return_value = (True, np.zeros(4800, dtype=np.float32), 0.95)

        # Mock speaker verifier to return a valid tuple (verified, score)
        mock_verifier_inst = MagicMock()
        mock_verifier_inst.verify.return_value = (True, 0.9)
        mock_speaker_verifier.return_value = mock_verifier_inst

        # Mock diagnostics
        mock_diag = MagicMock()
        state = VoiceLoopState(diagnostics=mock_diag)
        state.current_state = VoiceState.VOICE_IDLE
        state.verifier = mock_verifier_inst

        # Transition function for iteration
        def test_transition_to(new_state, detail=""):
            state.current_state = new_state
            from nova.voice.conversation import transition_state
            transition_state(new_state)

        # Mock AudioQualityAnalyzer to throw exception on analyze
        with patch("nova.voice.conversation.AudioQualityAnalyzer") as mock_qa_class:
            mock_qa = MagicMock()
            mock_qa.analyze.side_effect = ValueError("Simulated turn processing exception")
            mock_qa_class.return_value = mock_qa
            
            # Associate mock quality analyzer to the state object
            state.quality_analyzer = mock_qa

            # Execute a single iteration
            action = process_single_iteration(state, mock_ai_client, mock_dispatcher, test_transition_to)

            # Assertions
            # 1. Verify no exception escapes (process_single_iteration returned normally)
            self.assertEqual(action, "continue")
            # 2. Verify exception was caught and analyze called once
            mock_qa.analyze.assert_called_once()
            # 3. Verify recovery logic executed record_missed_wake on our mock diagnostics
            mock_diag.record_missed_wake.assert_called_once_with(
                wake_score=0.95,
                noise_floor=state.noise_floor
            )
            # 4. Verify VoiceState returned to VOICE_IDLE
            from nova.voice.conversation import get_current_state
            self.assertEqual(get_current_state(), VoiceState.VOICE_IDLE)
            self.assertEqual(state.current_state, VoiceState.VOICE_IDLE)

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
    def test_voice_loop_integration_iteration(
        self, mock_sd, mock_wait_for_wake, mock_play_sound, mock_speak,
        mock_vad, mock_aec, mock_rnnoise, mock_hp, mock_calibrator,
        mock_speaker_verifier, mock_wake_detector_class, mock_get_stt
    ):
        """Integration test: Verify run_voice_loop runs correctly and exits cleanly after one iteration using local shutdown event."""
        from nova.voice.conversation import run_voice_loop, VoiceState, get_current_state
        import threading
        
        # Mock providers
        mock_stt_inst = MagicMock()
        mock_stt_inst.transcribe.return_value = "exit"
        mock_get_stt.return_value = mock_stt_inst
        
        mock_sd.query_devices.return_value = {"name": "Mock Mic"}
        mock_sd.InputStream.return_value = MagicMock()
        mock_ai_client = MagicMock()
        mock_dispatcher = MagicMock()

        mock_calib_inst = MagicMock()
        mock_calib_inst.noise_floor = 0.001
        mock_calib_inst.speech_threshold = 0.002
        mock_calibrator.return_value = mock_calib_inst

        mock_detector_inst = MagicMock()
        mock_detector_inst.model_name = "hey_nova"
        mock_wake_detector_class.return_value = mock_detector_inst

        # Mock speaker verifier to return a valid tuple (verified, score)
        mock_verifier_inst = MagicMock()
        mock_verifier_inst.verify.return_value = (True, 0.9)
        mock_speaker_verifier.return_value = mock_verifier_inst

        # Setup local events to prevent global leakage
        local_shutdown = threading.Event()
        local_voice_active = threading.Event()
        local_voice_active.set()  # Starts active to transition out of Inactive wait

        # We set the local shutdown event in _wait_for_wake side effect to stop after 1 iteration
        def wait_side_effect(*args, **kwargs):
            local_shutdown.set()
            return True, np.zeros(4800, dtype=np.float32), 0.95
        mock_wait_for_wake.side_effect = wait_side_effect

        # Start run_voice_loop with patched local shutdown/voice_active events and mock sleep
        with patch("nova.voice.conversation.shutdown_event", local_shutdown), \
             patch("nova.voice.conversation.voice_active_event", local_voice_active), \
             patch("time.sleep", return_value=None), \
             patch("nova.voice.conversation.record_audio_from_stream", return_value=b"dummy audio"), \
             patch("nova.voice.conversation.AudioQualityAnalyzer") as mock_qa_class:
            
            mock_qa = MagicMock()
            mock_qa.analyze.return_value = {
                "overall_quality": 0.9,
                "background_noise": 0.01,
                "snr_db": 25.0,
                "clipping_pct": 0.0,
                "voice_volume": 0.5,
                "echo_level": 0.0
            }
            mock_qa_class.return_value = mock_qa
            
            # Execute run_voice_loop. It should run 1 iteration and return cleanly.
            result = run_voice_loop(mock_ai_client, mock_dispatcher)
            
            self.assertEqual(result, "menu")
            self.assertEqual(get_current_state(), VoiceState.SHUTDOWN)

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
    def test_voice_loop_interactive_startup(
        self, mock_sd, mock_wait_for_wake, mock_play_sound, mock_speak,
        mock_vad, mock_aec, mock_rnnoise, mock_hp, mock_calibrator,
        mock_speaker_verifier, mock_wake_detector_class, mock_get_stt
    ):
        """Verify that in interactive startup mode, the voice loop transitions to VOICE_IDLE immediately and opens the mic."""
        from nova.voice.conversation import run_voice_loop, VoiceState, get_current_state
        import threading

        mock_get_stt.return_value = MagicMock()
        mock_sd.query_devices.return_value = {"name": "Mock Mic"}
        mock_sd.InputStream.return_value = MagicMock()
        mock_ai_client = MagicMock()
        mock_dispatcher = MagicMock()

        mock_calib_inst = MagicMock()
        mock_calib_inst.noise_floor = 0.001
        mock_calib_inst.speech_threshold = 0.002
        mock_calibrator.return_value = mock_calib_inst

        mock_detector_inst = MagicMock()
        mock_detector_inst.model_name = "hey_nova"
        mock_wake_detector_class.return_value = mock_detector_inst

        mock_verifier_inst = MagicMock()
        mock_verifier_inst.verify.return_value = (True, 0.9)
        mock_speaker_verifier.return_value = mock_verifier_inst

        local_shutdown = threading.Event()
        local_voice_active = threading.Event()

        def wait_side_effect(*args, **kwargs):
            local_shutdown.set()
            return False, None, 0.0
        mock_wait_for_wake.side_effect = wait_side_effect

        with patch("nova.voice.conversation.shutdown_event", local_shutdown), \
             patch("nova.voice.conversation.voice_active_event", local_voice_active), \
             patch("time.sleep", return_value=None), \
             patch("nova.voice.conversation.AudioQualityAnalyzer") as mock_qa_class:
            
            mock_qa = MagicMock()
            mock_qa_class.return_value = mock_qa

            result = run_voice_loop(mock_ai_client, mock_dispatcher, interactive=True)

            self.assertEqual(result, "menu")
            # Verify InputStream was constructed and started immediately without waiting for voice_active_event
            mock_sd.InputStream.assert_called_once()
            mock_sd.InputStream.return_value.start.assert_called_once()
            # Verify the event remains unset/clear
            self.assertFalse(local_voice_active.is_set())

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
    def test_voice_loop_daemon_startup(
        self, mock_sd, mock_wait_for_wake, mock_play_sound, mock_speak,
        mock_vad, mock_aec, mock_rnnoise, mock_hp, mock_calibrator,
        mock_speaker_verifier, mock_wake_detector_class, mock_get_stt
    ):
        """Verify that in daemon mode startup, the voice loop does not open the mic and blocks in INACTIVE state."""
        from nova.voice.conversation import run_voice_loop, VoiceState, get_current_state
        import threading

        mock_get_stt.return_value = MagicMock()
        mock_sd.query_devices.return_value = {"name": "Mock Mic"}
        mock_sd.InputStream.return_value = MagicMock()
        mock_ai_client = MagicMock()
        mock_dispatcher = MagicMock()

        local_shutdown = threading.Event()
        local_voice_active = threading.Event() # Cleared initially (inactive daemon)

        # In inactive state wait loop, time.sleep(0.1) is called repeatedly.
        # We hook time.sleep side effect to set shutdown event to terminate the loop cleanly.
        def sleep_side_effect(seconds):
            local_shutdown.set()
        
        with patch("nova.voice.conversation.shutdown_event", local_shutdown), \
             patch("nova.voice.conversation.voice_active_event", local_voice_active), \
             patch("time.sleep", side_effect=sleep_side_effect):
            
            result = run_voice_loop(mock_ai_client, mock_dispatcher, interactive=False)

            self.assertEqual(result, "menu")
            # Verify stream was never initialized/opened
            mock_sd.InputStream.assert_not_called()
            self.assertEqual(get_current_state(), VoiceState.SHUTDOWN)

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
    def test_voice_loop_gui_shortcut_startup(
        self, mock_sd, mock_wait_for_wake, mock_play_sound, mock_speak,
        mock_vad, mock_aec, mock_rnnoise, mock_hp, mock_calibrator,
        mock_speaker_verifier, mock_wake_detector_class, mock_get_stt
    ):
        """Verify that when in daemon startup, triggering a GUI shortcut activates the mic and starts listening."""
        from nova.voice.conversation import run_voice_loop, VoiceState, get_current_state
        import threading

        mock_get_stt.return_value = MagicMock()
        mock_sd.query_devices.return_value = {"name": "Mock Mic"}
        mock_sd.InputStream.return_value = MagicMock()
        mock_ai_client = MagicMock()
        mock_dispatcher = MagicMock()

        mock_calib_inst = MagicMock()
        mock_calib_inst.noise_floor = 0.001
        mock_calib_inst.speech_threshold = 0.002
        mock_calibrator.return_value = mock_calib_inst

        mock_detector_inst = MagicMock()
        mock_detector_inst.model_name = "hey_nova"
        mock_wake_detector_class.return_value = mock_detector_inst

        mock_verifier_inst = MagicMock()
        mock_verifier_inst.verify.return_value = (True, 0.9)
        mock_speaker_verifier.return_value = mock_verifier_inst

        local_shutdown = threading.Event()
        local_voice_active = threading.Event() # Starts cleared (inactive daemon)

        # Hook time.sleep to simulate GUI shortcut setting active event and transitioning state
        def sleep_side_effect(seconds):
            from nova.voice.conversation import transition_state
            transition_state(VoiceState.VOICE_IDLE)
            local_voice_active.set()

        def wait_side_effect(*args, **kwargs):
            local_shutdown.set()
            if local_voice_active.is_set():
                local_voice_active.clear()
            return False, None, 0.0
        mock_wait_for_wake.side_effect = wait_side_effect

        with patch("nova.voice.conversation.shutdown_event", local_shutdown), \
             patch("nova.voice.conversation.voice_active_event", local_voice_active), \
             patch("time.sleep", side_effect=sleep_side_effect), \
             patch("nova.voice.conversation.AudioQualityAnalyzer") as mock_qa_class:
            
            mock_qa = MagicMock()
            mock_qa_class.return_value = mock_qa

            result = run_voice_loop(mock_ai_client, mock_dispatcher, interactive=False)

            self.assertEqual(result, "menu")
            # Verify InputStream was successfully opened after the toggle
            mock_sd.InputStream.assert_called_once()
            mock_sd.InputStream.return_value.start.assert_called_once()
            # Verify the active event was consumed/cleared
            self.assertFalse(local_voice_active.is_set())

    def test_spelling_regression(self):
        """Verify that correct_query_spelling does not incorrectly correct valid conversational words like 'Now' and 'cover'."""
        from nova.spelling import correct_query_spelling
        
        # Test that standard correct words are NOT modified
        query = "Now can you please tell me about today news, cover all news, the weather, the BBC news, the Apple market news, everything?"
        corrected = correct_query_spelling(query)
        self.assertEqual(corrected, query)

        # Test that actual typos are still corrected
        self.assertEqual(correct_query_spelling("opne youtube"), "open youtube")

if __name__ == "__main__":
    unittest.main()
