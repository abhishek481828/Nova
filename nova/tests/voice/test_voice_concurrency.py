import sys
import os
import unittest
import threading
try:
    import numpy as np
    from nova.voice.pipeline import transition_state, get_current_state, VoiceState
    from nova.voice.wakeword import LocalWakeWordDetector
    from nova.voice.whisper import WhisperSTTProvider
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False

from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestVoiceConcurrencyAndSafety(unittest.TestCase):

    def test_state_transition_concurrency(self):
        """Verify that transitions between conversation states are thread-safe and consistent."""
        states_to_test = [
            VoiceState.VOICE_IDLE,
            VoiceState.LISTENING,
            VoiceState.TRANSCRIBING,
            VoiceState.EXECUTING,
            VoiceState.SPEAKING,
            VoiceState.INACTIVE
        ]
        
        errors = []
        def worker(state):
            try:
                transition_state(state)
                curr = get_current_state()
                # Since multiple threads run concurrently, just ensure no exceptions are raised
                self.assertIn(curr, states_to_test)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(s,)) for s in states_to_test * 10]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread-safety errors in state machine: {errors}")

    @patch("faster_whisper.WhisperModel")
    def test_whisper_loader_thread_safety(self, mock_whisper_model):
        """Verify that double-checked locking works on the Whisper loader and loads it exactly once."""
        mock_instance = MagicMock()
        mock_whisper_model.return_value = mock_instance

        # Reset cached model
        WhisperSTTProvider._cached_model = None

        provider = WhisperSTTProvider(model_size="tiny")
        
        # Load concurrently across multiple threads
        threads = [threading.Thread(target=provider._load) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # WhisperModel should have been instantiated exactly once
        mock_whisper_model.assert_called_once()
        self.assertIsNotNone(WhisperSTTProvider._cached_model)

    @patch("openwakeword.model.Model")
    def test_wakeword_detect_dtype_conversion(self, mock_oww_model):
        """Verify that LocalWakeWordDetector.detect() converts float32 to int16 PCM (B36)."""
        mock_model_instance = MagicMock()
        mock_model_instance.predict.return_value = {"hey_nova_v0.1": 0.9}
        mock_oww_model.return_value = mock_model_instance

        # Initialize detector with a dummy model path
        with patch("os.path.exists", return_value=True):
            detector = LocalWakeWordDetector(model_path="/dummy/hey_nova_v0.1.onnx", confidence_threshold=0.5)

        # Pass 1280 samples of float32 audio
        float32_audio = np.ones((1280, 1), dtype=np.float32) * 0.1
        res = detector.detect(float32_audio, sample_rate=16000)

        self.assertTrue(res)
        
        # The predicted frame passed to the ONNX model must be an int16 array
        called_args = mock_model_instance.predict.call_args[0][0]
        self.assertEqual(called_args.dtype, np.int16)
        self.assertEqual(len(called_args), 1280)

if __name__ == "__main__":
    unittest.main()
