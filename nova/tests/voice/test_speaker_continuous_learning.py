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

import nova.voice.config as cfg

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestSpeakerContinuousLearning(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.emb_path = os.path.join(self.tmp_dir.name, "speaker_embedding.bin")
        self.meta_path = os.path.join(self.tmp_dir.name, "speaker_meta.json")

    def tearDown(self):
        self.tmp_dir.cleanup()

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", True)
    @patch("nova.voice.speaker.preprocess_wav", create=True, side_effect=lambda x, **kw: x)
    def test_staged_pending_adaptation(self, mock_prep):
        """Verify that verify() stages candidates as pending adaptation instead of writing directly."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        
        # Enroll initial anchors
        emb1 = np.zeros(256)
        emb1[0] = 1.0
        emb2 = np.zeros(256)
        emb2[1] = 1.0
        emb3 = np.zeros(256)
        emb3[2] = 1.0
        
        verifier._embeddings = np.vstack([emb1, emb2, emb3])
        verifier._profile_meta = {
            "version": "2.0",
            "enrolled_at": "2026-06-30T12:00:00Z",
            "embeddings": [
                {"id": 0, "is_anchor": True, "quality_score": 1.0, "speaking_condition": "enrollment"},
                {"id": 1, "is_anchor": True, "quality_score": 1.0, "speaking_condition": "enrollment"},
                {"id": 2, "is_anchor": True, "quality_score": 1.0, "speaking_condition": "enrollment"}
            ]
        }
        verifier._save_profile()
        
        # Mock encoder query
        query_emb = np.zeros(256)
        query_emb[0] = 0.99  # very close to emb1
        
        mock_encoder = MagicMock()
        mock_encoder.embed_utterance.return_value = query_emb
        verifier._encoder = mock_encoder
        
        # Call verify
        is_match, score = verifier.verify(np.ones(16000), sr=16000)
        self.assertTrue(is_match)
        
        # Check that it is staged but NOT committed yet
        self.assertIsNotNone(verifier._pending_adaptation)
        self.assertEqual(len(verifier._embeddings), 3) # count remains 3

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", True)
    def test_clear_pending_adaptation(self):
        """Verify clear_pending_adaptation() discards staged candidate."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        verifier._pending_adaptation = (np.zeros(256), np.ones(16000), 16000)
        
        verifier.clear_pending_adaptation()
        self.assertIsNone(verifier._pending_adaptation)

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", True)
    def test_anchor_based_drift_rejection(self):
        """Verify that candidates deviating from anchors are rejected to prevent drift."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        
        # Setup anchors (centered on indices 0, 1, 2)
        emb1 = np.zeros(256)
        emb1[0] = 1.0
        emb2 = np.zeros(256)
        emb2[1] = 1.0
        emb3 = np.zeros(256)
        emb3[2] = 1.0
        
        verifier._embeddings = np.vstack([emb1, emb2, emb3])
        verifier._profile_meta = {
            "version": "2.0",
            "enrolled_at": "2026-06-30T12:00:00Z",
            "embeddings": [
                {"id": 0, "is_anchor": True, "quality_score": 1.0, "speaking_condition": "enrollment"},
                {"id": 1, "is_anchor": True, "quality_score": 1.0, "speaking_condition": "enrollment"},
                {"id": 2, "is_anchor": True, "quality_score": 1.0, "speaking_condition": "enrollment"}
            ]
        }
        verifier._save_profile()
        
        # 1. Staged candidate that drifts (high similarity to index 10, but 0.0 to all anchors)
        drift_emb = np.zeros(256)
        drift_emb[10] = 1.0
        verifier._pending_adaptation = (drift_emb, np.ones(32000) * 0.05, 16000)
        
        # Commit should reject it due to drift threshold (0.70)
        verifier.commit_adaptation()
        self.assertEqual(len(verifier._embeddings), 3) # stays 3
        
        # 2. Staged candidate close to anchor emb1 (similarity = 0.95)
        good_emb = np.zeros(256)
        good_emb[0] = 0.95
        good_emb[5] = np.sqrt(1 - 0.95**2)  # normalize
        verifier._pending_adaptation = (good_emb, np.ones(32000) * 0.05, 16000)
        
        # Commit should succeed
        verifier.commit_adaptation()
        self.assertEqual(len(verifier._embeddings), 4) # increases to 4
        self.assertFalse(verifier._profile_meta["embeddings"][3]["is_anchor"])

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", True)
    def test_backup_and_rollback(self):
        """Verify rollback restores profile state from backup files."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        
        # Setup initial profile
        emb1 = np.zeros(256)
        emb1[0] = 1.0
        verifier._embeddings = emb1.reshape(1, 256)
        verifier._profile_meta = {
            "version": "2.0",
            "enrolled_at": "2026-06-30T12:00:00Z",
            "embeddings": [
                {"id": 0, "is_anchor": True, "quality_score": 1.0, "speaking_condition": "enrollment"}
            ]
        }
        verifier._save_profile()
        
        # Stage and commit new embedding
        good_emb = np.zeros(256)
        good_emb[0] = 0.95
        good_emb[5] = np.sqrt(1 - 0.95**2)
        verifier._pending_adaptation = (good_emb, np.ones(32000) * 0.05, 16000)
        
        verifier.commit_adaptation()
        self.assertEqual(len(verifier._embeddings), 2)
        
        # Perform rollback
        self.assertTrue(verifier.rollback())
        
        # Verify state is restored to 1 embedding
        self.assertEqual(len(verifier._embeddings), 1)
        self.assertEqual(len(verifier._profile_meta["embeddings"]), 1)

    @patch("nova.voice.speaker._RESEMBLYZER_AVAILABLE", True)
    def test_disabled_via_config(self):
        """Verify continuous learning is skipped when configuration is disabled."""
        verifier = SpeakerVerifier(embedding_path=self.emb_path)
        
        # Initial profile
        emb1 = np.zeros(256)
        emb1[0] = 1.0
        verifier._embeddings = emb1.reshape(1, 256)
        verifier._profile_meta = {
            "version": "2.0",
            "enrolled_at": "2026-06-30T12:00:00Z",
            "embeddings": [
                {"id": 0, "is_anchor": True, "quality_score": 1.0, "speaking_condition": "enrollment"}
            ]
        }
        verifier._save_profile()
        
        good_emb = np.zeros(256)
        good_emb[0] = 0.95
        good_emb[5] = np.sqrt(1 - 0.95**2)
        verifier._pending_adaptation = (good_emb, np.ones(32000) * 0.05, 16000)
        
        # Disable continuous learning in configuration
        with patch.object(cfg, "ENABLE_SPEAKER_CONTINUOUS_LEARNING", False):
            verifier.commit_adaptation()
            
        # Verify it was NOT committed and candidate was cleared
        self.assertEqual(len(verifier._embeddings), 1)
        self.assertIsNone(verifier._pending_adaptation)

if __name__ == "__main__":
    unittest.main()
