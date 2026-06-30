"""
Confidence Fusion Engine for Nova.

Combines multiple indicators (wake-word, speaker verification, WebRTC VAD,
audio quality, and noise estimation) into a single unified decision score.
Weights are fully configurable and dynamically normalised to handle disabled
or missing confidence sources at runtime.
Supports registering custom future confidence providers.
"""

import time
import os
import json
from nova.logger import logger
import nova.voice.config as cfg

class ConfidenceFusionEngine:
    def __init__(self, weights: dict[str, float] = None) -> None:
        # Default weights from configuration if not provided
        self.weights = weights or {
            "wake": getattr(cfg, "FUSION_WEIGHT_WAKE", 0.40),
            "speaker": getattr(cfg, "FUSION_WEIGHT_SPEAKER", 0.30),
            "vad": getattr(cfg, "FUSION_WEIGHT_VAD", 0.15),
            "quality": getattr(cfg, "FUSION_WEIGHT_QUALITY", 0.10),
            "noise": getattr(cfg, "FUSION_WEIGHT_NOISE", 0.05)
        }
        
        # Extensible custom sources registry: list of tuples (name, weight, callable)
        # The callable should accept the kwargs and return a float in [0.0, 1.0]
        self._custom_sources = []
        
        # Diagnostics
        self.diagnostics_path = os.path.expanduser("~/.config/nova/fusion_logs.json")
        self.history = []

    def register_source(self, name: str, weight: float, scorer_callable: callable) -> None:
        """Register a future/custom confidence scorer source."""
        # Clean any existing source with same name
        self._custom_sources = [s for s in self._custom_sources if s[0] != name]
        self._custom_sources.append((name, weight, scorer_callable))
        self.weights[name] = weight
        logger.info(f"Registered custom confidence source '{name}' with weight {weight:.3f}")

    def fuse(
        self,
        wake_score: float,
        speaker_score: float | None = None,
        vad_score: float | None = None,
        audio_quality: float | None = None,
        noise_level: float | None = None,
        **kwargs
    ) -> float:
        """
        Combines confidence inputs into a single score.
        Gracefully handles missing (None) inputs by dynamically normalising
        weights of active inputs.
        """
        raw_inputs = {
            "wake": wake_score,
            "speaker": speaker_score,
            "vad": vad_score,
            "quality": audio_quality,
        }
        
        # Convert noise level to confidence (low noise = high confidence, high noise = low confidence)
        if noise_level is not None:
            # Scale noise floor. Max noise floor is ~0.1, above that is fully noisy.
            raw_inputs["noise"] = max(0.0, 1.0 - (noise_level * 10.0))
        else:
            raw_inputs["noise"] = None

        # Process custom sources
        for name, _, scorer_callable in self._custom_sources:
            try:
                score = scorer_callable(**kwargs)
                raw_inputs[name] = float(score) if score is not None else None
            except Exception as e:
                logger.debug(f"Custom confidence source '{name}' failed: {e}")
                raw_inputs[name] = None

        # Filter active inputs
        active_scores = {}
        for name, score in raw_inputs.items():
            if score is not None:
                # Clamp between 0.0 and 1.0
                active_scores[name] = min(1.0, max(0.0, float(score)))

        if not active_scores:
            return 0.0

        # Dynamically normalise active weights
        active_weights = {}
        total_weight = 0.0
        for name in active_scores:
            w = self.weights.get(name, 0.0)
            active_weights[name] = w
            total_weight += w

        if total_weight < 1e-9:
            # Fall back to equal weighting if all weights are zero
            equal_w = 1.0 / len(active_scores)
            active_weights = {name: equal_w for name in active_scores}
            total_weight = 1.0

        # Calculate weighted sum
        fused_score = 0.0
        for name, score in active_scores.items():
            normalized_weight = active_weights[name] / total_weight
            fused_score += score * normalized_weight

        # Log diagnostics
        self._log_diagnostics(active_scores, active_weights, total_weight, fused_score)

        return min(1.0, max(0.0, float(fused_score)))

    def _log_diagnostics(self, scores: dict, weights: dict, total_weight: float, fused: float) -> None:
        diag = {
            "timestamp": time.time(),
            "event": "confidence_fusion",
            "scores": {k: float(v) for k, v in scores.items()},
            "weights": {k: float(v / total_weight) for k, v in weights.items()},
            "fused_score": float(fused)
        }
        self.history.append(diag)
        # Cap in-memory history to prevent memory growth (Critical check)
        self.history = self.history[-500:]
        
        # Use non-blocking async logger (Critical optimization)
        from nova.voice.async_logging import async_log
        async_log(self.diagnostics_path, diag, 500)

