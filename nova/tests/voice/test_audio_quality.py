import sys
import os
import unittest
try:
    import numpy as np
    from nova.voice.pipeline import AudioQualityAnalyzer
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False


# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestAudioQuality(unittest.TestCase):

    def test_snr_and_background_noise(self):
        """Verify SNR and background noise estimations on synthetic signals."""
        analyzer = AudioQualityAnalyzer()
        
        # 1. Create a quiet background noise signal (RMS = 0.002)
        np.random.seed(42)
        noise = np.random.randn(4800).astype(np.float32) * 0.002
        
        # 2. Add some "speech" frames with higher amplitude (RMS = 0.05)
        speech = np.sin(2 * np.pi * 100 * np.linspace(0, 0.1, 1600)).astype(np.float32) * 0.07
        audio = noise.copy()
        audio[1600:3200] += speech
        
        metrics = analyzer.analyze(audio)
        
        # Background noise should be close to 0.002
        self.assertAlmostEqual(metrics["background_noise"], 0.002, delta=0.001)
        # SNR should be positive and significant (> 15 dB)
        self.assertGreater(metrics["snr_db"], 15.0)

    def test_clipping_pct(self):
        """Verify clipping percentage calculation."""
        analyzer = AudioQualityAnalyzer()
        
        # Create a signal of 1000 samples, with exactly 10 samples clipped at 1.0
        audio = np.zeros(1000, dtype=np.float32)
        audio[:10] = 1.0
        
        metrics = analyzer.analyze(audio)
        self.assertAlmostEqual(metrics["clipping_pct"], 1.0, places=4)

    def test_echo_level(self):
        """Verify echo level estimation via normalized cross-correlation."""
        analyzer = AudioQualityAnalyzer()
        
        # 1. Identical signals (perfect echo)
        sig1 = np.random.randn(1000).astype(np.float32) * 0.1
        sig2 = sig1.copy()
        
        metrics_perfect = analyzer.analyze(sig1, ref_audio=sig2)
        self.assertGreater(metrics_perfect["echo_level"], 0.95)
        
        # 2. Uncorrelated signals (no echo)
        sig3 = np.random.randn(1000).astype(np.float32) * 0.1
        metrics_none = analyzer.analyze(sig1, ref_audio=sig3)
        self.assertLess(metrics_none["echo_level"], 0.20)

    def test_overall_quality_score(self):
        """Verify overall quality score behavior under different conditions."""
        analyzer = AudioQualityAnalyzer()
        
        # 1. Perfect clean signal (low noise floor + active sine wave speech)
        np.random.seed(42)
        noise = np.random.randn(4800).astype(np.float32) * 0.0001
        speech = np.sin(2 * np.pi * 100 * np.linspace(0, 0.2, 3200)).astype(np.float32) * 0.05
        clean_audio = noise.copy()
        clean_audio[800:4000] += speech
        
        metrics_clean = analyzer.analyze(clean_audio)
        self.assertGreater(metrics_clean["overall_quality"], 0.70)
        
        # 2. Clipped signal (severely penalizes quality)
        clipped_audio = clean_audio.copy()
        clipped_audio[:200] = 1.0
        metrics_clipped = analyzer.analyze(clipped_audio)
        self.assertLess(metrics_clipped["overall_quality"], 0.20)
        
        # 3. High noise floor signal
        noisy_audio = np.random.randn(4800).astype(np.float32) * 0.15
        metrics_noisy = analyzer.analyze(noisy_audio)
        self.assertLessEqual(metrics_noisy["overall_quality"], 0.30)

    def test_api_keys(self):
        """Verify that the analyze API returns all required metrics."""
        analyzer = AudioQualityAnalyzer()
        audio = np.zeros(480, dtype=np.float32)
        
        metrics = analyzer.analyze(audio)
        expected_keys = {
            "snr_db", "background_noise", "clipping_pct",
            "voice_volume", "echo_level", "overall_quality"
        }
        self.assertEqual(set(metrics.keys()), expected_keys)

if __name__ == "__main__":
    unittest.main()
