import sys
import os
import unittest
try:
    import numpy as np
    from nova.voice.wakeword import LocalWakeWordDetector
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False

import tempfile
import json
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestWakeWordUpgrades(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        # Create a dummy ONNX model file so detector initialization passes
        self.dummy_model_path = os.path.join(self.tmp_dir.name, "hey_test_wake.onnx")
        with open(self.dummy_model_path, "wb") as f:
            f.write(b"mock onnx content")

    def tearDown(self):
        self.tmp_dir.cleanup()

    @patch("openwakeword.model.Model")
    def test_init_multiple_wake_phrases(self, mock_oww_model):
        """Verify multiple wake word phrase paths are resolved and loaded."""
        # Create multiple dummy ONNX model files
        model_p1 = os.path.join(self.tmp_dir.name, "hey_nova.onnx")
        model_p2 = os.path.join(self.tmp_dir.name, "hey_jarvis.onnx")
        with open(model_p1, "wb") as f: f.write(b"mock1")
        with open(model_p2, "wb") as f: f.write(b"mock2")

        detector = LocalWakeWordDetector(
            model_path=[model_p1, model_p2],
            confidence_threshold=0.5
        )
        
        self.assertEqual(detector.model_names, ["hey_nova", "hey_jarvis"])
        self.assertEqual(detector.model_name, "hey_nova")
        mock_oww_model.assert_called_once_with(wakeword_model_paths=[model_p1, model_p2])

    @patch("openwakeword.model.Model")
    def test_rolling_audio_buffer(self, mock_oww_model):
        """Verify audio samples accumulate correctly in the rolling buffer and compute valid RMS."""
        detector = LocalWakeWordDetector(model_path=self.dummy_model_path, confidence_threshold=0.5)
        
        # Feed 1000 samples of 1000 amplitude
        pcm_chunk = np.ones(1000, dtype=np.int16) * 1000
        detector._process_rolling_audio(pcm_chunk)
        
        self.assertEqual(detector.buffer_index, 1000)
        self.assertFalse(detector.buffer_filled)
        
        # Verify RMS is approximately 1000 / 32768 = 0.0305
        current_rms = detector.get_current_rms()
        self.assertAlmostEqual(current_rms, 1000.0 / 32768.0, places=4)

    @patch("openwakeword.model.Model")
    def test_adaptive_threshold(self, mock_oww_model):
        """Verify that confidence thresholds scale up dynamically under high noise floor."""
        detector = LocalWakeWordDetector(model_path=self.dummy_model_path, confidence_threshold=0.5)
        
        # Under quiet noise floor (0.001), threshold should remain at base (0.5)
        detector.noise_floor = 0.001
        self.assertEqual(detector.get_adaptive_threshold(), 0.5)
        
        # Under high noise floor (0.025), threshold should scale up
        detector.noise_floor = 0.025
        adaptive_thresh = detector.get_adaptive_threshold()
        self.assertGreater(adaptive_thresh, 0.5)
        self.assertLessEqual(adaptive_thresh, 0.95)

    @patch("openwakeword.model.Model")
    def test_diagnostics_logging_and_auto_tuning(self, mock_oww_model):
        """Verify false/missed triggers update counts, adjust threshold, and write json logs."""
        detector = LocalWakeWordDetector(model_path=self.dummy_model_path, confidence_threshold=0.5)
        
        # Set a temporary diagnostics path inside our temp dir
        detector.diagnostics_path = os.path.join(self.tmp_dir.name, "wake_logs.json")
        
        # Register a false wake
        detector.log_false_wake("hey_test_wake", score=0.9, rms=0.01)
        self.assertEqual(detector.false_wake_count, 1)
        # Threshold should increase on false wake
        self.assertGreater(detector.confidence_threshold, 0.5)
        
        # Register a missed wake
        prev_threshold = detector.confidence_threshold
        detector.log_missed_wake("hey_test_wake", score=0.45, rms=0.015)
        self.assertEqual(detector.missed_wake_count, 1)
        # Threshold should decrease on missed wake
        self.assertLess(detector.confidence_threshold, prev_threshold)
        
        # Flush async logger to disk before asserting (Critical async test update)
        from nova.voice.pipeline import _async_logger
        _async_logger.flush()

        # Check if the diagnostics log file was written and is valid JSON
        self.assertTrue(os.path.exists(detector.diagnostics_path))
        with open(detector.diagnostics_path, "r") as f:
            logs = json.load(f)
            
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["event"], "false_wake")
        self.assertEqual(logs[1]["event"], "missed_wake")

if __name__ == "__main__":
    unittest.main()
