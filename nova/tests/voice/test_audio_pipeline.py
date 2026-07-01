import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

try:
    import numpy as np
    from nova.voice.pipeline import (
        AmbientCalibrator,
        AutomaticGainControl,
        WebRTCVoiceActivityDetector,
        RNNoiseWrapper,
        HighPassFilter
    )
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestAudioPipelineUpgrades(unittest.TestCase):

    def test_ambient_calibration_transient_rejection(self):
        """Verify that AmbientCalibrator filters out impulse click spikes."""
        calibrator = AmbientCalibrator()
        
        # 2 seconds of audio (32000 samples) at 16kHz
        # Baseline noise floor is 0.001 RMS
        ambient_noise = np.random.randn(32000).astype(np.float32) * 0.001
        
        # Introduce a large click spike in a single frame (e.g. sample index 5000 to 5200)
        ambient_noise[5000:5200] = 0.5
        
        # Calibration using 10th percentile
        calibrator.calibrate(ambient_noise, frame_size=480)
        
        # The noise floor should remain close to the baseline noise of 0.001,
        # completely rejecting the 0.5 spike!
        self.assertLess(calibrator.noise_floor, 0.01)
        self.assertGreater(calibrator.noise_floor, 0.0)

    def test_agc_noise_pumping_prevention(self):
        """Verify that AGC freezes gain adaptation when speech is inactive or signal is below noise gate."""
        # Setup AGC with a noise floor threshold of 0.01
        agc = AutomaticGainControl(target_rms=0.08, max_gain=8.0, rate=0.5, noise_floor=0.01)
        agc.current_gain = 2.0
        
        # Feed low RMS input (e.g. 0.002, which is below noise_floor * 1.5)
        quiet_signal = np.ones((480, 1), dtype=np.float32) * 0.002
        
        # Process with speech_active=True, but signal is below noise gate:
        # Adaptation should be frozen (gain remains 2.0)
        agc.process(quiet_signal, speech_active=True)
        self.assertEqual(agc.current_gain, 2.0)
        
        # Feed louder RMS input (0.05, above noise gate), but with speech_active=False
        loud_signal = np.ones((480, 1), dtype=np.float32) * 0.05
        agc.process(loud_signal, speech_active=False)
        self.assertEqual(agc.current_gain, 2.0)
        
        # Process with speech_active=True and louder signal:
        # Adaptation should trigger (gain should decrease since target is 0.08 and signal is 0.05, 0.05*2.0 = 0.1 > 0.08)
        agc.process(loud_signal, speech_active=True)
        self.assertLess(agc.current_gain, 2.0)

    @patch("webrtcvad.Vad")
    def test_webrtc_vad_arbitrary_sizes_and_hangover(self, mock_vad_cls):
        """Verify WebRTC VAD handles non-standard sizes without crashes and implements hangover."""
        # Mock Vad.is_speech to return True first (first block of Frame 1), then False for all subsequent blocks
        mock_vad = MagicMock()
        mock_vad.is_speech.side_effect = [True] + [False] * 20
        mock_vad_cls.return_value = mock_vad

        vad = WebRTCVoiceActivityDetector(aggressiveness=2, default_threshold=0.01, hangover_frames=3)
        
        # Frame 1: returns True (from mock) -> sets counter to 3
        frame = np.ones(500, dtype=np.float32) * 0.05
        self.assertTrue(vad.is_speech(frame, sample_rate=16000))
        self.assertEqual(vad.hangover_counter, 3)
        
        # Frame 2: mock returns False -> decrements to 2, still returns True
        silent_frame = np.zeros(500, dtype=np.float32)
        self.assertTrue(vad.is_speech(silent_frame, sample_rate=16000))
        self.assertEqual(vad.hangover_counter, 2)
        
        # Frame 3: mock returns False -> decrements to 1, still returns True
        self.assertTrue(vad.is_speech(silent_frame, sample_rate=16000))
        self.assertEqual(vad.hangover_counter, 1)

        # Frame 4: mock returns False -> decrements to 0, still returns True
        self.assertTrue(vad.is_speech(silent_frame, sample_rate=16000))
        self.assertEqual(vad.hangover_counter, 0)
        
        # Frame 5: mock returns False -> counter is 0, returns False
        self.assertFalse(vad.is_speech(silent_frame, sample_rate=16000))

    def test_rnnoise_arbitrary_sizes(self):
        """Verify that RNNoise wrapper handles non-standard chunk sizes through padding."""
        rnnoise = RNNoiseWrapper()
        
        # Feed arbitrary chunk size (e.g. 500 samples)
        dummy_chunk = np.random.randn(500).astype(np.float32) * 0.01
        
        # Should process without crash
        result = rnnoise.denoise_chunk(dummy_chunk)
        self.assertEqual(result.shape, dummy_chunk.shape)
        
        rnnoise.destroy()

    def test_highpass_filter_nyquist_safety(self):
        """Verify that HighPassFilter handles cutoff limits above Nyquist limit gracefully."""
        # Cutoff at 9000 Hz, sample rate 16000 Hz (Nyquist is 8000 Hz).
        # This is invalid, so it should bypass butterworth filter creation and copy signal.
        filt = HighPassFilter(cutoff=9000.0, fs=16000.0)
        self.assertIsNone(filt.sos)
        self.assertIsNone(filt._zi)
        
        signal = np.ones((100, 1), dtype=np.float32) * 0.5
        result = filt.process(signal)
        
        # Output should be identical (bypassed)
        np.testing.assert_array_equal(result, signal)

if __name__ == "__main__":
    unittest.main()
