import sys
import os
import unittest
import tempfile
import json
import time

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

try:
    from nova.voice.pipeline import ConfidenceFusionEngine
    _NUMPY_AVAILABLE = True
except ImportError:
    ConfidenceFusionEngine = None  # type: ignore
    _NUMPY_AVAILABLE = False

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestConfidenceFusionEngine(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.diagnostics_path = os.path.join(self.tmp_dir.name, "fusion_logs.json")

    def tearDown(self):
        from nova.voice.pipeline import _async_logger
        _async_logger.flush()
        self.tmp_dir.cleanup()

    def test_default_weighted_fusion(self):
        """Verify fused score matches expected weighted sum when all inputs are present."""
        # Using simple test weights
        weights = {
            "wake": 0.5,
            "speaker": 0.3,
            "vad": 0.2
        }
        engine = ConfidenceFusionEngine(weights=weights)
        engine.diagnostics_path = self.diagnostics_path
        
        # Inputs: wake=0.8, speaker=0.7, vad=0.9
        # Expected: 0.8*0.5 + 0.7*0.3 + 0.9*0.2 = 0.4 + 0.21 + 0.18 = 0.79
        fused = engine.fuse(wake_score=0.8, speaker_score=0.7, vad_score=0.9)
        self.assertAlmostEqual(fused, 0.79, places=4)

    def test_dynamic_weight_normalization_on_missing_inputs(self):
        """Verify weights are dynamically normalised when some inputs are missing."""
        weights = {
            "wake": 0.4,
            "speaker": 0.4,
            "vad": 0.2
        }
        engine = ConfidenceFusionEngine(weights=weights)
        engine.diagnostics_path = self.diagnostics_path
        
        # Inputs: wake=0.8, speaker=None, vad=0.6
        # Active weights: wake=0.4, vad=0.2. Total active weight = 0.6
        # Normalised weights: wake = 0.4 / 0.6 = 2/3, vad = 0.2 / 0.6 = 1/3
        # Expected: 0.8 * (2/3) + 0.6 * (1/3) = 0.5333 + 0.2000 = 0.7333
        fused = engine.fuse(wake_score=0.8, vad_score=0.6)
        self.assertAlmostEqual(fused, 0.7333, places=4)

    def test_noise_level_to_confidence_mapping(self):
        """Verify that high noise levels reduce confidence and map correctly."""
        weights = {
            "wake": 0.8,
            "noise": 0.2
        }
        engine = ConfidenceFusionEngine(weights=weights)
        engine.diagnostics_path = self.diagnostics_path
        
        # 1. Quiet environment: noise_level = 0.001
        # noise confidence = 1.0 - 0.001 * 10 = 0.99
        # Expected: 0.8 * 0.8 + 0.99 * 0.2 = 0.64 + 0.198 = 0.838
        fused_quiet = engine.fuse(wake_score=0.8, noise_level=0.001)
        self.assertAlmostEqual(fused_quiet, 0.838, places=4)

        # 2. Noisy environment: noise_level = 0.05
        # noise confidence = 1.0 - 0.05 * 10 = 0.50
        # Expected: 0.8 * 0.8 + 0.5 * 0.2 = 0.64 + 0.10 = 0.740
        fused_noisy = engine.fuse(wake_score=0.8, noise_level=0.05)
        self.assertAlmostEqual(fused_noisy, 0.740, places=4)

    def test_custom_source_registration_and_fusion(self):
        """Verify that custom scorers can be registered, executed via kwargs, and fuse correctly."""
        weights = {
            "wake": 0.6,
            "speaker": 0.4
        }
        engine = ConfidenceFusionEngine(weights=weights)
        engine.diagnostics_path = self.diagnostics_path
        
        # Register custom source "sentiment" with weight 0.20
        # Expected new weights mapping: wake=0.6, speaker=0.4, sentiment=0.2. Total active = 1.2
        # Normalised weights: wake=0.5, speaker=0.333, sentiment=0.1667
        engine.register_source(
            name="sentiment",
            weight=0.2,
            scorer_callable=lambda **kw: kw.get("sentiment_val", 0.5)
        )
        
        # Fuse with custom kwarg sentiment_val=0.90
        # Inputs: wake=0.8, speaker=0.6, custom sentiment=0.9
        # Total weight = 0.6 + 0.4 + 0.2 = 1.2
        # Fused = (0.8*0.6 + 0.6*0.4 + 0.9*0.2) / 1.2 = (0.48 + 0.24 + 0.18) / 1.2 = 0.90 / 1.2 = 0.75
        fused = engine.fuse(wake_score=0.8, speaker_score=0.6, sentiment_val=0.9)
        self.assertAlmostEqual(fused, 0.75, places=4)

    def test_diagnostics_integration(self):
        """Verify diagnostics history is stored in-memory and written as valid JSON logs."""
        weights = {"wake": 1.0}
        engine = ConfidenceFusionEngine(weights=weights)
        engine.diagnostics_path = self.diagnostics_path
        
        engine.fuse(wake_score=0.85)
        engine.fuse(wake_score=0.95)
        
        # Assert in-memory history has 2 records
        self.assertEqual(len(engine.history), 2)
        self.assertEqual(engine.history[0]["fused_score"], 0.85)
        self.assertEqual(engine.history[1]["fused_score"], 0.95)
        
        # Flush async logger to disk before asserting (Critical async test update)
        from nova.voice.pipeline import _async_logger
        _async_logger.flush()

        # Assert log file is written and contains valid records
        self.assertTrue(os.path.exists(self.diagnostics_path))
        with open(self.diagnostics_path, "r") as f:
            logs = json.load(f)
            
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["scores"]["wake"], 0.85)
        self.assertEqual(logs[1]["scores"]["wake"], 0.95)

if __name__ == "__main__":
    unittest.main()
