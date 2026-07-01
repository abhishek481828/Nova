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
import nova.voice.config as cfg

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
    Upgraded to a multi-embedding profile system (version 2.0) with:
      - Continuous speaker learning (staged commit after successful interactions)
      - Profile drift prevention via anchor enrollment embeddings
      - Capacity limit enforcement and quality-based cleanup
      - Backups and rollback functionality
      - Configurable toggle support
    """

    def __init__(self, embedding_path: str, threshold: float = 0.75) -> None:
        self._emb_path  = Path(embedding_path)
        self._meta_path = self._emb_path.with_name("speaker_meta.json")
        self._threshold = threshold
        self._encoder: Optional["VoiceEncoder"] = None

        # Multi-embedding paths (version 2.0)
        self._profile_path = self._emb_path.with_name("speaker_profile.json")
        self._embeddings_npy_path = self._emb_path.with_name("speaker_embeddings.npy")

        # Pending adaptations staging layer
        self._pending_adaptation: Optional[tuple[np.ndarray, np.ndarray, int]] = None

        # Resolve legacy bin path (np.save appends .npy automatically)
        self._legacy_bin_path = self._emb_path
        if not self._legacy_bin_path.exists():
            npy_path = self._emb_path.with_name(self._emb_path.name + ".npy")
            if npy_path.exists():
                self._legacy_bin_path = npy_path

        self._embeddings: Optional[np.ndarray] = None
        self._profile_meta: dict = {
            "version": "2.0",
            "enrolled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "embeddings": []
        }

        # 1. Automatic migration from legacy files if they exist
        if self._legacy_bin_path.exists() and not self._profile_path.exists():
            self._migrate_legacy_profile()

        # 2. Eagerly load multi-embedding profile if it exists
        self._load_profile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True if Resemblyzer is importable."""
        return _RESEMBLYZER_AVAILABLE

    def has_profile(self) -> bool:
        """Return True if a valid speaker profile (version 2.0) is stored on disk."""
        return self._profile_path.exists() and self._embeddings is not None and len(self._embeddings) > 0

    @property
    def total_embeddings(self) -> int:
        """Returns the total number of embeddings in the active profile."""
        return len(self._embeddings) if self._embeddings is not None else 0

    @property
    def max_capacity(self) -> int:
        """Returns the maximum embeddings capacity from configuration."""
        return getattr(cfg, "MAX_EMBEDDINGS", 50)

    def enroll(self, audio_list: list[np.ndarray], sr: int = 16000) -> None:
        """
        Enroll from a list of raw float32 numpy arrays (one per recording).
        Extracts embeddings, scores quality, and marks them as anchors.
        """
        if not _RESEMBLYZER_AVAILABLE:
            raise RuntimeError(
                "resemblyzer is not installed.\n"
                "Run:  pip install resemblyzer"
            )
        if len(audio_list) < 3:
            raise ValueError("Need at least 3 audio samples for reliable enrollment.")

        encoder = self._get_encoder()
        new_embeddings = []
        new_metadata = []

        for idx, audio in enumerate(audio_list):
            try:
                # 1. Evaluate utterance quality
                quality_score, rms = self._evaluate_quality(audio, sr)
                if quality_score < 0.2:
                    logger.debug(f"Enrollment sample index {idx} skipped: quality too low ({quality_score:.2f})")
                    continue

                wav = preprocess_wav(audio.flatten(), source_sr=sr)
                if len(wav) < sr * 0.3:
                    continue
                emb = encoder.embed_utterance(wav)
                
                # Normalize
                emb = emb / (np.linalg.norm(emb) + 1e-9)
                new_embeddings.append(emb)
                new_metadata.append({
                    "id": idx,
                    "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "quality_score": float(quality_score),
                    "speaking_condition": "enrollment",
                    "rms": float(rms),
                    "is_anchor": True  # Tag as anchor embedding for drift prevention
                })
            except Exception as e:
                logger.debug(f"Enrollment sample index {idx} skipped: {e}")

        if len(new_embeddings) < 3:
            raise RuntimeError("Too many bad/short samples — enrollment failed.")

        # Reset existing profile structures on new enrollment
        self._embeddings = np.array(new_embeddings)
        self._profile_meta = {
            "version": "2.0",
            "enrolled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "embeddings": new_metadata
        }
        
        self._save_profile()
        logger.info(f"Speaker profile enrolled with {len(new_embeddings)} multi-embeddings.")

    def verify(self, audio: np.ndarray, sr: int = 16000) -> tuple[bool, float]:
        """
        Compare ``audio`` against all stored speaker embeddings.
        Stages potential adaptations as pending without committing them immediately.
        """
        # Fail-open: if we cannot verify, always allow
        if not _RESEMBLYZER_AVAILABLE or self._embeddings is None or len(self._embeddings) == 0:
            return True, 1.0

        try:
            # Check for silent audio first to prevent Resemblyzer exception (division by zero)
            rms = float(np.sqrt(np.mean(audio ** 2)))
            if rms < 0.001:  # too quiet to be meaningful speech
                logger.debug(f"Speaker verification skipped: audio too quiet (RMS={rms:.6f})")
                # Return None score so the fusion engine skips this signal
                # rather than treating it as "definitely not the owner"
                return True, None

            encoder = self._get_encoder()
            wav = preprocess_wav(audio.flatten(), source_sr=sr)
            if len(wav) < sr * 0.3:          # too short to be meaningful
                return True, None
                
            emb = encoder.embed_utterance(wav)
            emb = emb / (np.linalg.norm(emb) + 1e-9)

            similarities = np.dot(self._embeddings, emb)
            max_score = float(np.max(similarities))
            
            is_match = max_score >= self._threshold
            
            # Continuous learning staging: stage high-confidence utterances for adaptation
            if is_match and max_score > 0.85:
                self._pending_adaptation = (emb, audio, sr)
            else:
                self._pending_adaptation = None

            return is_match, max_score
        except Exception as e:
            logger.debug(f"Speaker verification error (failing closed for invalid audio): {e}")
            return False, 0.0

    def commit_adaptation(self) -> None:
        """
        Commits any pending speaker adaptation to the profile.
        """
        if self._pending_adaptation is None:
            return

        # Check configuration
        if not getattr(cfg, "ENABLE_SPEAKER_CONTINUOUS_LEARNING", True):
            self._pending_adaptation = None
            return

        emb, audio, sr = self._pending_adaptation
        self._pending_adaptation = None

        try:
            self._adapt_profile(emb, audio, sr)
        except Exception as e:
            logger.debug(f"Continuous speaker verification learning error: {e}")

    def _adapt_profile(self, embedding: np.ndarray, audio: np.ndarray, sr: int, max_embeddings: Optional[int] = None) -> None:
        """Dynamically add high-confidence validation utterances to adapt to noise/conditions."""
        if max_embeddings is None:
            max_embeddings = getattr(cfg, "MAX_EMBEDDINGS", 50)
        # 1. Reject duplicate
        if self._is_duplicate(embedding):
            return

        # 2. Score quality
        quality, rms = self._evaluate_quality(audio, sr)
        if quality < 0.3:
            return

        # 3. Anchor-based drift checks
        # Collect all anchor indices
        anchor_indices = []
        for idx, item in enumerate(self._profile_meta.get("embeddings", [])):
            if item.get("is_anchor", False):
                anchor_indices.append(idx)

        # Fallback: if no anchors (e.g. legacy migrated profile), treat first item as anchor
        if not anchor_indices and self._embeddings is not None and len(self._embeddings) > 0:
            anchor_indices = [0]
            self._profile_meta["embeddings"][0]["is_anchor"] = True

        if anchor_indices and self._embeddings is not None:
            anchor_vecs = self._embeddings[anchor_indices]
            drift_similarities = np.dot(anchor_vecs, embedding)
            drift_thresh = getattr(cfg, "SPEAKER_DRIFT_THRESHOLD", 0.70)
            # Verify candidate is similar enough to at least one anchor to prevent drift
            if np.max(drift_similarities) < drift_thresh:
                logger.warning(
                    f"Speaker voice adaptation rejected to prevent profile drift. "
                    f"Max similarity to anchors: {np.max(drift_similarities):.3f} (threshold: {drift_thresh})"
                )
                return

        # 4. Save session backup for rollback support
        self._backup_profile()

        # 5. Commit adaptation
        new_meta = {
            "id": len(self._profile_meta["embeddings"]),
            "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "quality_score": float(quality),
            "speaking_condition": "dynamic_adaptation",
            "rms": float(rms),
            "is_anchor": False
        }

        self._profile_path.parent.mkdir(parents=True, exist_ok=True)

        if self._embeddings is None or len(self._embeddings) == 0:
            self._embeddings = embedding.reshape(1, 256)
            self._profile_meta["embeddings"] = [new_meta]
        else:
            if len(self._embeddings) >= max_embeddings:
                # Cleanup: remove the lowest quality non-anchor embedding
                lowest_idx = -1
                lowest_quality = 1.1
                for idx, item in enumerate(self._profile_meta["embeddings"]):
                    # Never delete anchors
                    if item.get("is_anchor", False):
                        continue
                    q = item.get("quality_score", 1.0)
                    if q < lowest_quality:
                        lowest_quality = q
                        lowest_idx = idx

                # Fallback to oldest FIFO if all are anchors or no lower score
                if lowest_idx == -1:
                    # Find first non-anchor to remove
                    for idx, item in enumerate(self._profile_meta["embeddings"]):
                        if not item.get("is_anchor", False):
                            lowest_idx = idx
                            break

                if lowest_idx != -1:
                    self._embeddings = np.delete(self._embeddings, lowest_idx, axis=0)
                    self._profile_meta["embeddings"].pop(lowest_idx)
                    logger.info(f"Enforcing profile limit. Removed low-quality embedding index {lowest_idx}.")

            self._embeddings = np.vstack([self._embeddings, embedding])
            self._profile_meta["embeddings"].append(new_meta)

        self._profile_meta["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save_profile()
        logger.info(f"Learned new speaker embedding. Total embeddings: {len(self._embeddings)}")

    def clear_pending_adaptation(self) -> None:
        """Discard any staged candidate speaker adaptation."""
        self._pending_adaptation = None

    def rollback(self) -> bool:
        """Roll back the speaker profile to the state before the most recent adaptation."""
        bak_profile = self._profile_path.with_suffix(".json.bak")
        bak_embeddings = self._embeddings_npy_path.with_name(self._embeddings_npy_path.name + ".bak")

        if bak_profile.exists() and bak_embeddings.exists():
            try:
                import shutil
                shutil.copy(str(bak_profile), str(self._profile_path))
                shutil.copy(str(bak_embeddings), str(self._embeddings_npy_path))
                self._load_profile()
                logger.info("Rolled back speaker verification profile to previous backup state.")
                return True
            except Exception as e:
                logger.debug(f"Failed to rollback speaker profile: {e}")
        return False

    def delete_profile(self) -> bool:
        """Delete stored profile files. Returns True if anything was deleted."""
        deleted = False
        paths_to_delete = [
            self._emb_path,
            self._meta_path,
            self._profile_path,
            self._embeddings_npy_path,
            self._profile_path.with_suffix(".json.bak"),
            self._embeddings_npy_path.with_name(self._embeddings_npy_path.name + ".bak")
        ]
        for path in paths_to_delete:
            if path.exists():
                try:
                    path.unlink()
                    deleted = True
                except Exception:
                    pass
        self._embeddings = None
        self._profile_meta = {
            "version": "2.0",
            "enrolled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "embeddings": []
        }
        return deleted

    def meta(self) -> Optional[dict]:
        """Return profile metadata, maintaining backward compatibility."""
        if not self._profile_path.exists():
            # Fallback to legacy metadata check
            if self._meta_path.exists():
                try:
                    return json.loads(self._meta_path.read_text())
                except Exception:
                    pass
            return None
        return self._profile_meta

    # ------------------------------------------------------------------
    # Internal helpers & profile management
    # ------------------------------------------------------------------

    def _get_encoder(self) -> "VoiceEncoder":
        """Lazy-load the GE2E encoder."""
        if self._encoder is None:
            self._encoder = VoiceEncoder(device="cpu")
        return self._encoder

    def _migrate_legacy_profile(self) -> None:
        """Automatically migrates a legacy 1.0 profile to 2.0 multi-embedding system."""
        try:
            legacy_emb = np.load(str(self._legacy_bin_path))
            if legacy_emb.ndim == 1 and len(legacy_emb) == 256:
                # L2-normalize
                legacy_emb = legacy_emb / (np.linalg.norm(legacy_emb) + 1e-9)
                
                enrolled_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if self._meta_path.exists():
                    try:
                        meta_data = json.loads(self._meta_path.read_text())
                        enrolled_time = meta_data.get("enrolled_at", enrolled_time)
                    except Exception:
                        pass
                
                self._embeddings = legacy_emb.reshape(1, 256)
                self._profile_meta = {
                    "version": "2.0",
                    "enrolled_at": enrolled_time,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "embeddings": [
                        {
                            "id": 0,
                            "added_at": enrolled_time,
                            "quality_score": 1.0,
                            "speaking_condition": "legacy_migration",
                            "rms": 0.05,
                            "is_anchor": True  # Mark migrated mean as an anchor
                        }
                    ]
                }
                self._save_profile()
                logger.info("Successfully migrated legacy speaker profile to version 2.0 layout.")
                
                # Delete legacy files
                if self._legacy_bin_path.exists():
                    self._legacy_bin_path.unlink()
                if self._meta_path.exists():
                    self._meta_path.unlink()
        except Exception as e:
            logger.debug(f"Failed to migrate legacy profile: {e}")

    def _load_profile(self) -> None:
        if self._profile_path.exists() and self._embeddings_npy_path.exists():
            try:
                self._profile_meta = json.loads(self._profile_path.read_text())
                self._embeddings = np.load(str(self._embeddings_npy_path))
                # Enforce L2 normalization in loaded matrix
                for i in range(len(self._embeddings)):
                    self._embeddings[i] = self._embeddings[i] / (np.linalg.norm(self._embeddings[i]) + 1e-9)
            except Exception as e:
                logger.debug(f"Failed to load speaker profile: {e}")

    def _save_profile(self) -> None:
        try:
            self._profile_path.parent.mkdir(parents=True, exist_ok=True)
            self._profile_path.write_text(json.dumps(self._profile_meta, indent=2))
            if self._embeddings is not None:
                np.save(str(self._embeddings_npy_path), self._embeddings)
        except Exception as e:
            logger.debug(f"Failed to save speaker profile: {e}")

    def _backup_profile(self) -> None:
        try:
            if self._profile_path.exists():
                shutil_copy = self._profile_path.with_suffix(".json.bak")
                shutil_copy.write_text(self._profile_path.read_text())
            if self._embeddings_npy_path.exists() and self._embeddings is not None:
                import shutil
                bak_npy = self._embeddings_npy_path.with_name(self._embeddings_npy_path.name + ".bak")
                shutil.copy(str(self._embeddings_npy_path), str(bak_npy))
        except Exception as e:
            logger.debug(f"Failed to backup speaker profile: {e}")

    def _evaluate_quality(self, audio: np.ndarray, sr: int) -> tuple[float, float]:
        flat = audio.flatten()
        rms = float(np.sqrt(np.mean(flat * flat)))
        duration = len(flat) / sr

        # Quality scoring out of 1.0: duration maps to 0.5, RMS maps to 0.5
        duration_score = min(0.5, (duration / 2.0) * 0.5)
        
        if 0.01 <= rms <= 0.15:
            rms_score = 0.5
        elif rms > 0.15:
            rms_score = max(0.0, 0.5 - (rms - 0.15) * 0.5)
        else:
            rms_score = (rms / 0.01) * 0.5
            
        return min(1.0, duration_score * rms_score * 4.0), rms

    def _is_duplicate(self, embedding: np.ndarray, threshold: float = 0.98) -> bool:
        if self._embeddings is None or len(self._embeddings) == 0:
            return False
        similarities = np.dot(self._embeddings, embedding)
        return bool(np.any(similarities >= threshold))
