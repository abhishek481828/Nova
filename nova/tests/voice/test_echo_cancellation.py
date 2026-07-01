import sys
import os
import unittest
try:
    import numpy as np
    from nova.voice.pipeline import AecProcessor, SpeexEchoCanceller, NLMSEchoCanceller, get_reference_chunk
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False

import time
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

import nova.voice.config as cfg

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestEchoCancellation(unittest.TestCase):

    def setUp(self):
        # Save config settings
        self.saved_enable_aec = cfg.ENABLE_ECHO_CANCEL
        cfg.ENABLE_ECHO_CANCEL = True
        
        # Save voice_config aec variables
        import nova.voice.config as voice_config
        self.saved_ref_audio = getattr(voice_config, "aec_reference_audio", None)
        self.saved_start_time = getattr(voice_config, "aec_playback_start_time", None)

    def tearDown(self):
        cfg.ENABLE_ECHO_CANCEL = self.saved_enable_aec
        import nova.voice.config as voice_config
        voice_config.aec_reference_audio = self.saved_ref_audio
        voice_config.aec_playback_start_time = self.saved_start_time

    def test_aec_processor_fallback(self):
        """Verify that AecProcessor instantiates and falls back correctly if Speex is unavailable."""
        aec = AecProcessor(frame_size=480, filter_len=1600)
        self.assertIsNotNone(aec)
        if aec.speex_aec.is_available():
            self.assertIsNone(aec.nlms_aec)
        else:
            self.assertIsNotNone(aec.nlms_aec)
            self.assertIsInstance(aec.nlms_aec, NLMSEchoCanceller)

    def test_nlms_echo_canceller_convergence(self):
        """Verify mathematically that NLMS adaptive filter converges and reduces echo energy."""
        # 240 taps (15ms tail), frame size 480, larger step size for fast convergence
        canceller = NLMSEchoCanceller(frame_size=480, filter_len=240, mu=0.5, eps=1e-3)
        
        # Generate synthetic reference signal: white noise
        np.random.seed(42)
        play_signal = np.random.randn(4800).astype(np.float32) * 0.1
        
        # Create echo path: simple delay and scaling
        # echo[n] = 0.5 * play_signal[n - 10]
        echo_path_delay = 10
        echo_scaling = 0.5
        
        # Pure echo recording
        rec_signal = np.zeros_like(play_signal)
        rec_signal[echo_path_delay:] = echo_scaling * play_signal[:-echo_path_delay]
        
        # Run NLMS block-by-block (10 blocks of 480 samples)
        n_blocks = len(play_signal) // 480
        out_signal = np.zeros_like(rec_signal)
        
        for b in range(n_blocks):
            offset = b * 480
            play_chunk = play_signal[offset : offset + 480]
            rec_chunk = rec_signal[offset : offset + 480]
            out_signal[offset : offset + 480] = canceller.process(rec_chunk, play_chunk)
            
        # Calculate echo energy in the last block (where filter has converged)
        last_block_offset = (n_blocks - 1) * 480
        last_block_output = out_signal[last_block_offset : last_block_offset + 480]
        last_block_rec = rec_signal[last_block_offset : last_block_offset + 480]
        
        rec_energy = np.mean(np.square(last_block_rec))
        aec_energy = np.mean(np.square(last_block_output))
        
        # AEC residual energy should be extremely close to zero (echo cancelled!)
        self.assertLess(aec_energy, 1e-6)
        self.assertLess(aec_energy, rec_energy * 1e-4)

    def test_reference_chunk_sync(self):
        """Verify that get_reference_chunk correctly extracts time-synced audio frames."""
        import nova.voice.config as voice_config
        
        # Setup dummy reference audio: 2 seconds of sound
        ref_audio = np.ones(32000, dtype=np.float32) * 0.5
        voice_config.aec_reference_audio = ref_audio
        voice_config.aec_playback_start_time = time.time() - 0.5 # 0.5 seconds elapsed (8000 samples)
        
        chunk = get_reference_chunk(480)
        self.assertIsNotNone(chunk)
        self.assertEqual(len(chunk), 480)
        np.testing.assert_array_almost_equal(chunk, np.ones(480) * 0.5)
        
        # If elapsed time exceeds play length, returns None
        voice_config.aec_playback_start_time = time.time() - 3.0
        chunk_ended = get_reference_chunk(480)
        self.assertIsNone(chunk_ended)

    def test_aec_disabled_bypass(self):
        """Verify that when ENABLE_ECHO_CANCEL is False, AEC returns original audio unmodified."""
        cfg.ENABLE_ECHO_CANCEL = False
        
        aec = AecProcessor(frame_size=480, filter_len=1600)
        mic_chunk = np.ones(480, dtype=np.float32)
        
        # Even if playback is active
        import nova.voice.config as voice_config
        voice_config.aec_reference_audio = np.ones(10000, dtype=np.float32)
        voice_config.aec_playback_start_time = time.time()
        
        processed = aec.process(mic_chunk)
        np.testing.assert_array_equal(processed, mic_chunk)

    def test_latency_benchmark(self):
        """Benchmark execution latency of Speex and NLMS echo cancellers."""
        canceller = NLMSEchoCanceller(frame_size=480, filter_len=1600)
        rec = np.random.randn(480).astype(np.float32)
        play = np.random.randn(480).astype(np.float32)
        
        # Warmup
        for _ in range(5):
            canceller.process(rec, play)
            
        t0 = time.time()
        runs = 100
        for _ in range(runs):
            canceller.process(rec, play)
        duration_ms = (time.time() - t0) * 1000.0 / runs
        
        print(f"\n[BENCHMARK] NLMS Echo Canceller average chunk latency: {duration_ms:.3f} ms")
        self.assertLess(duration_ms, 8.0) # NLMS must take less than 8ms (well within 30ms chunk limit)

if __name__ == "__main__":
    unittest.main()
