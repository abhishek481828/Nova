import sys
import os
import unittest
import tempfile
import json
import time
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

try:
    from nova.voice.wakeword import AdaptiveWakeController
    import nova.voice.config as cfg
    _NUMPY_AVAILABLE = True
except ImportError:
    AdaptiveWakeController = cfg = None  # type: ignore
    _NUMPY_AVAILABLE = False

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestAdaptiveWake(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.logs_path = os.path.join(self.tmp_dir.name, "adaptive_wake_logs.json")
        self.wake_logs_path = os.path.join(self.tmp_dir.name, "wake_logs.json")
        
        # Clear any environment variables that would override
        self.env_overrides = ["NOVA_WAKE_WORD_CONFIDENCE", "WAKE_WORD_CONFIDENCE",
                              "NOVA_VAD_THRESHOLD", "VAD_THRESHOLD",
                              "NOVA_SILENCE_TIMEOUT", "SILENCE_TIMEOUT",
                              "NOVA_SPEAKER_THRESHOLD", "SPEAKER_THRESHOLD"]
        self.saved_env = {}
        for var in self.env_overrides:
            if var in os.environ:
                self.saved_env[var] = os.environ[var]
                del os.environ[var]

    def tearDown(self):
        for var, val in self.saved_env.items():
            os.environ[var] = val
        from nova.voice.pipeline import _async_logger
        _async_logger.flush()
        self.tmp_dir.cleanup()

    def test_noise_scaling_thresholds(self):
        """Verify thresholds scale up under high environmental noise."""
        controller = AdaptiveWakeController()
        controller.logs_path = self.logs_path
        controller.wake_logs_path = self.wake_logs_path
        
        # 1. Quiet environment: noise floor 0.0001
        res_quiet = controller.adapt(noise_floor=0.0001)
        
        # 2. Noisy environment: noise floor 0.04
        res_noisy = controller.adapt(noise_floor=0.04)
        
        # Wake confidence and VAD thresholds should be higher in noisy environments
        self.assertGreater(res_noisy["wake_threshold"], res_quiet["wake_threshold"])
        self.assertGreater(res_noisy["vad_threshold"], res_quiet["vad_threshold"])

    def test_silence_timeout_scaling(self):
        """Verify silence timeout expands under poor SNR or high noise floor."""
        controller = AdaptiveWakeController()
        controller.logs_path = self.logs_path
        controller.wake_logs_path = self.wake_logs_path
        
        # 1. High noise floor (0.015)
        res_noisy = controller.adapt(noise_floor=0.015)
        self.assertEqual(res_noisy["silence_timeout"], 3.0)
        
        # 2. Poor SNR (8 dB)
        res_low_snr = controller.adapt(noise_floor=0.0005, signal_quality_snr=8.0)
        self.assertEqual(res_low_snr["silence_timeout"], 3.2)

    def test_speaker_threshold_snr_scaling(self):
        """Verify speaker verification threshold reduces under poor SNR to avoid rejections."""
        controller = AdaptiveWakeController()
        controller.logs_path = self.logs_path
        controller.wake_logs_path = self.wake_logs_path
        
        # 1. Perfect SNR (25 dB)
        res_clear = controller.adapt(noise_floor=0.0005, signal_quality_snr=25.0)
        
        # 2. Poor SNR (10 dB)
        res_poor = controller.adapt(noise_floor=0.0005, signal_quality_snr=10.0)
        
        self.assertLess(res_poor["speaker_threshold"], res_clear["speaker_threshold"])

    def test_historical_trigger_adaptation(self):
        """Verify low trigger success rates increase wake and speaker thresholds to be strict."""
        controller = AdaptiveWakeController()
        controller.logs_path = self.logs_path
        controller.wake_logs_path = self.wake_logs_path
        
        # Write mock logs showing high false trigger rates (1 success, 9 false wakes)
        logs = [{"event": "wake_trigger", "is_false_wake": True}] * 9
        logs.append({"event": "wake_trigger", "is_false_wake": False})
        
        with open(self.wake_logs_path, "w") as f:
            json.dump(logs, f)
            
        res = controller.adapt(noise_floor=0.0005)
        
        # Wake threshold should be strict (>0.60) and speaker verification strict (>0.75)
        self.assertGreaterEqual(res["wake_threshold"], 0.60)
        self.assertGreaterEqual(res["speaker_threshold"], 0.75)

    def test_user_override_preservation(self):
        """Verify user overrides defined in environment variables are strictly preserved."""
        controller = AdaptiveWakeController()
        controller.logs_path = self.logs_path
        controller.wake_logs_path = self.wake_logs_path
        
        # Apply environment variable overrides
        os.environ["NOVA_WAKE_WORD_CONFIDENCE"] = "0.80"
        os.environ["NOVA_VAD_THRESHOLD"] = "0.007"
        
        # Run adaptation with extremely high noise
        res = controller.adapt(noise_floor=0.05)
        
        # Overridden values must remain untouched
        self.assertEqual(res["wake_threshold"], 0.80)
        self.assertEqual(res["vad_threshold"], 0.007)

    def test_adaptation_logging(self):
        """Verify adaptation events are successfully appended to the logs JSON file."""
        controller = AdaptiveWakeController()
        controller.logs_path = self.logs_path
        controller.wake_logs_path = self.wake_logs_path
        
        # Trigger an adaptation change
        controller.adapt(noise_floor=0.03)
        
        # Flush async logger to disk before asserting (Critical async test update)
        from nova.voice.pipeline import _async_logger
        _async_logger.flush()

        # Verify log file is written and contains the event details
        self.assertTrue(os.path.exists(self.logs_path))
        with open(self.logs_path, "r") as f:
            events = json.load(f)
            
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]["inputs"]["noise_floor"], 0.03, places=4)
        self.assertTrue(len(events[0]["reasons"]) > 0)

if __name__ == "__main__":
    unittest.main()
