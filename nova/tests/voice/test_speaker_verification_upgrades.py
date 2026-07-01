import sys
import os
import unittest
try:
    import numpy as np
    from nova.voice.speaker import SpeakerVerifier
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
class TestSpeakerVerificationUpgrades(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.emb_path = os.path.join(self.tmp_dir.name, "speaker_embedding.bin")
        self.meta_path = os.path.join(self.tmp_dir.name, "speaker_meta.json")

    def tearDown(self):
        self.tmp_dir.cleanup()

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", True)
    def test_legacy_profile_migration(self):
        """Verify that legacy 1.0 profile binary and json are automatically migrated to 2.0 system."""
        # Create legacy files
        legacy_emb = np.random.randn(256).astype(np.float32)
        legacy_emb /= np.linalg.norm(legacy_emb)
        np.save(self.emb_path, legacy_emb)
        
        legacy_meta = {"samples": 3, "enrolled_at": "2026-06-30T12:00:00Z"}
        with open(self.meta_path, "w") as f:
            json.dump(legacy_meta, f)
            
        # Instantiate SpeakerVerifier
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        
        # Verify legacy files were deleted and migrated version 2.0 files created
        self.assertFalse(os.path.exists(self.emb_path))
        self.assertFalse(os.path.exists(self.meta_path))
        
        profile_path = os.path.join(self.tmp_dir.name, "speaker_profile.json")
        embeddings_npy_path = os.path.join(self.tmp_dir.name, "speaker_embeddings.npy")
        
        self.assertTrue(os.path.exists(profile_path))
        self.assertTrue(os.path.exists(embeddings_npy_path))
        
        # Load and verify content
        with open(profile_path, "r") as f:
            profile_meta = json.load(f)
            
        self.assertEqual(profile_meta["version"], "2.0")
        self.assertEqual(profile_meta["enrolled_at"], "2026-06-30T12:00:00Z")
        self.assertEqual(len(profile_meta["embeddings"]), 1)
        self.assertEqual(profile_meta["embeddings"][0]["speaking_condition"], "legacy_migration")
        
        embeddings_matrix = np.load(embeddings_npy_path)
        self.assertEqual(embeddings_matrix.shape, (1, 256))
        np.testing.assert_array_almost_equal(embeddings_matrix[0], legacy_emb, decimal=5)

    def test_quality_score_estimation(self):
        """Verify quality evaluation score is correct based on length and RMS."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        
        # 1. High-quality audio: 2 seconds at 16kHz with moderate amplitude (0.05 RMS)
        good_audio = np.ones(32000, dtype=np.float32) * 0.05
        quality, rms = verifier._evaluate_quality(good_audio, sr=16000)
        self.assertGreater(quality, 0.7)
        self.assertAlmostEqual(rms, 0.05, places=4)
        
        # 2. Quiet audio: RMS is extremely small (0.0005)
        quiet_audio = np.ones(32000, dtype=np.float32) * 0.0005
        quality, rms = verifier._evaluate_quality(quiet_audio, sr=16000)
        self.assertLess(quality, 0.5)

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", True)
    def test_duplicate_detection(self):
        """Verify that identical or highly similar embeddings are recognized as duplicates."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        
        # Create a dummy 2.0 profile matrix with 2 embeddings
        emb1 = np.zeros(256)
        emb1[0] = 1.0  # L2 normalized
        emb2 = np.zeros(256)
        emb2[1] = 1.0  # L2 normalized
        verifier._embeddings = np.vstack([emb1, emb2])
        
        # Test query that is identical to emb1
        self.assertTrue(verifier._is_duplicate(emb1, threshold=0.98))
        
        # Test query that is different
        different_emb = np.zeros(256)
        different_emb[2] = 1.0
        self.assertFalse(verifier._is_duplicate(different_emb, threshold=0.98))

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", True)
    def test_automatic_cleanup_capacity(self):
        """Verify that profile automatically trims the lowest-quality embedding when capacity limit is reached."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        
        # Setup initial embeddings matrix of shape [3, 256] where all share index 0 for drift check alignment
        emb0 = np.zeros(256)
        emb0[0] = 1.0
        emb1 = np.zeros(256)
        emb1[0] = 1.0
        emb2 = np.zeros(256)
        emb2[0] = 1.0
        verifier._embeddings = np.vstack([emb0, emb1, emb2])
            
        verifier._profile_meta = {
            "version": "2.0",
            "enrolled_at": "2026-06-30T12:00:00Z",
            "embeddings": [
                {"id": 0, "is_anchor": True, "quality_score": 0.9, "speaking_condition": "enrollment"},
                {"id": 1, "is_anchor": False, "quality_score": 0.3, "speaking_condition": "enrollment"}, # <-- lowest quality non-anchor
                {"id": 2, "is_anchor": True, "quality_score": 0.8, "speaking_condition": "enrollment"}
            ]
        }
        
        # Add new embedding (L2 normalized) with similarity 0.95 to anchors
        new_emb = np.zeros(256)
        new_emb[0] = 0.95
        new_emb[5] = np.sqrt(1 - 0.95**2)
        
        dummy_audio = np.ones(16000) * 0.05 # high quality
        
        # This should trigger cleanup of the lowest-quality embedding (index 1, id=1, quality_score=0.3)
        verifier._adapt_profile(new_emb, dummy_audio, sr=16000, max_embeddings=3)
        
        # Total embeddings count should remain 3
        self.assertEqual(len(verifier._embeddings), 3)
        self.assertEqual(len(verifier._profile_meta["embeddings"]), 3)
        
        # Verified that the item with id=1 was deleted
        remaining_ids = [item["id"] for item in verifier._profile_meta["embeddings"]]
        self.assertNotIn(1, remaining_ids)

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", False)
    def test_resemblyzer_unavailable_fail_open(self):
        """Verify verification fails open (returns True, 1.0) when Resemblyzer is not installed."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        is_match, score = verifier.verify(np.ones(16000), sr=16000)
        self.assertTrue(is_match)
        self.assertEqual(score, 1.0)

if __name__ == "__main__":
    unittest.main()
