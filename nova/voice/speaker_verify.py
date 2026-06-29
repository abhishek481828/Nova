"""
Speaker verification module for Nova.

Uses Resemblyzer (GE2E speaker encoder) to produce 256-dim d-vectors.
If Resemblyzer is not installed the module degrades gracefully — all
public methods still work, but verify() always returns (True, 1.0) so
the rest of the pipeline is unaffected.

Storage layout  (~/.config/nova/ by default):
  speaker_embedding.bin   — numpy npy file: mean 256-dim d-vector
  speaker_meta.json       — JSON: {"samples": N, "enrolled_at": ISO8601}

Raw audio is NEVER written to disk.
"""

from __future__ import annotations

import json
import os
import time
import numpy as np
from pathlib import Path
from typing import Optional

from nova.logger import logger

# ---------------------------------------------------------------------------
# Attempt to import Resemblyzer at module load time.
# A failed import disables speaker verification silently.
# ---------------------------------------------------------------------------
try:
    from resemblyzer import VoiceEncoder, preprocess_wav   # type: ignore
    _RESEMBLYZER_AVAILABLE = True
except ImportError:
    _RESEMBLYZER_AVAILABLE = False
    logger.debug("resemblyzer not installed — speaker verification will be skipped.")


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two flat vectors.  Returns value in [-1, 1]."""
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-9:
        return 0.0
    return float(np.dot(a, b) / denom)


class SpeakerVerifier:
    """
    Enroll a speaker once, verify against every subsequent wake trigger.

    Parameters
    ----------
    embedding_path : str
        Path to `speaker_embedding.bin` (numpy npy).
    threshold : float
        Minimum cosine-similarity score to accept a speaker.
    """

    def __init__(self, embedding_path: str, threshold: float = 0.75) -> None:
        self._emb_path  = Path(embedding_path)
        self._meta_path = self._emb_path.with_name("speaker_meta.json")
        self._threshold = threshold
        self._embedding: Optional[np.ndarray] = None
        self._encoder: Optional["VoiceEncoder"] = None

        # Load existing profile eagerly so verification is fast at runtime
        if self._emb_path.exists():
            try:
                self._embedding = np.load(str(self._emb_path))
            except Exception as e:
                logger.debug(f"Failed to load speaker embedding: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True if Resemblyzer is importable."""
        return _RESEMBLYZER_AVAILABLE

    def has_profile(self) -> bool:
        """Return True if a valid speaker profile is stored on disk."""
        return self._emb_path.exists() and self._embedding is not None

    def enroll(self, audio_list: list[np.ndarray], sr: int = 16000) -> None:
        """
        Enroll from a list of raw float32 numpy arrays (one per recording).
        Saves only the mean d-vector; raw audio is discarded immediately.

        Raises
        ------
        RuntimeError
            If Resemblyzer is not available or fewer than 3 samples are given.
        """
        if not _RESEMBLYZER_AVAILABLE:
            raise RuntimeError(
                "resemblyzer is not installed.\n"
                "Run:  pip install resemblyzer"
            )
        if len(audio_list) < 3:
            raise ValueError("Need at least 3 audio samples for reliable enrollment.")

        encoder = self._get_encoder()
        embeddings = []
        for audio in audio_list:
            try:
                wav = preprocess_wav(audio.flatten(), source_sr=sr)
                emb = encoder.embed_utterance(wav)
                embeddings.append(emb)
            except Exception as e:
                logger.debug(f"Enrollment sample skipped ({e})")

        if len(embeddings) < 3:
            raise RuntimeError("Too many bad samples — enrollment failed.")

        mean_emb = np.mean(embeddings, axis=0)
        mean_emb /= np.linalg.norm(mean_emb)   # L2 normalise

        # Persist
        self._emb_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(self._emb_path), mean_emb)
        meta = {
            "samples": len(embeddings),
            "enrolled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._meta_path.write_text(json.dumps(meta, indent=2))

        self._embedding = mean_emb
        logger.info(f"Speaker profile enrolled from {len(embeddings)} samples.")

    def verify(
        self, audio: np.ndarray, sr: int = 16000
    ) -> tuple[bool, float]:
        """
        Compare ``audio`` against the enrolled speaker profile.

        Returns
        -------
        (is_match, similarity_score)
            is_match : True if the speaker passes the threshold (or if
                       verification is unavailable — fail-open policy).
            similarity_score : float in [0, 1]; 1.0 means identical.
        """
        # Fail-open: if we cannot verify, always allow
        if not _RESEMBLYZER_AVAILABLE or self._embedding is None:
            return True, 1.0

        try:
            encoder = self._get_encoder()
            wav = preprocess_wav(audio.flatten(), source_sr=sr)
            if len(wav) < sr * 0.3:          # too short to be meaningful
                return True, 1.0
            emb = encoder.embed_utterance(wav)
            score = _cosine_similarity(self._embedding, emb)
            return score >= self._threshold, float(score)
        except Exception as e:
            logger.debug(f"Speaker verification error (fail-open): {e}")
            return True, 1.0   # fail-open on any exception

    def delete_profile(self) -> bool:
        """Delete stored profile files.  Returns True if anything was deleted."""
        deleted = False
        for path in (self._emb_path, self._meta_path):
            if path.exists():
                path.unlink()
                deleted = True
        self._embedding = None
        return deleted

    def meta(self) -> Optional[dict]:
        """Return metadata dict, or None if no profile is enrolled."""
        if not self._meta_path.exists():
            return None
        try:
            return json.loads(self._meta_path.read_text())
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_encoder(self) -> "VoiceEncoder":
        """Lazy-load the GE2E encoder (downloads model on first call)."""
        if self._encoder is None:
            self._encoder = VoiceEncoder(device="cpu")
        return self._encoder
