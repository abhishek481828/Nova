"""
Adaptive Wake Behaviour module for Nova.

Automatically adjusts wake thresholds, VAD thresholds, silence timeouts,
and speaker verification thresholds based on environmental noise floor,
measured speech SNR, microphone clipping rates, and historical success rates.
Preserves manual user overrides and logs all adaptations.
"""

import os
import json
import time
from nova.logger import logger
import nova.voice.config as cfg

class AdaptiveWakeController:
    def __init__(self) -> None:
        self.logs_path = os.path.expanduser("~/.config/nova/adaptive_wake_logs.json")
        self.wake_logs_path = os.path.expanduser("~/.config/nova/wake_logs.json")

    def get_historical_success_rate(self) -> float:
        """Calculate the recent trigger success rate from wake_logs.json."""
        if not os.path.exists(self.wake_logs_path):
            return 1.0 # assume perfect success initially
        try:
            with open(self.wake_logs_path, "r") as f:
                logs = json.load(f)
            if not isinstance(logs, list) or not logs:
                return 1.0
            
            # Look at last 30 events
            recent = logs[-30:]
            total = len(recent)
            successful = sum(1 for item in recent if item.get("event") == "wake_trigger" and not item.get("is_false_wake", False))
            return float(successful / total)
        except Exception:
            return 1.0

    def adapt(
        self,
        noise_floor: float,
        signal_quality_snr: float | None = None,
        clipping_pct: float | None = None
    ) -> dict[str, float]:
        """
        Evaluate inputs and calculate adapted threshold parameters.
        Maintains user environment variable overrides.
        """
        # Read historical success rate
        success_rate = self.get_historical_success_rate()

        # Capture old/current config values
        old_vals = {
            "wake_threshold": float(getattr(cfg, "WAKE_WORD_CONFIDENCE", 0.50)),
            "vad_threshold": float(getattr(cfg, "VAD_THRESHOLD", 0.001)),
            "silence_timeout": float(getattr(cfg, "SILENCE_TIMEOUT", 2.0)),
            "speaker_threshold": float(getattr(cfg, "SPEAKER_THRESHOLD", 0.75)) # default threshold parameter or config
        }

        new_vals = old_vals.copy()
        reasons = []

        # ---------------------------------------------------------
        # 1. Adapt Wake Threshold (WAKE_WORD_CONFIDENCE)
        # ---------------------------------------------------------
        if "NOVA_WAKE_WORD_CONFIDENCE" in os.environ or "WAKE_WORD_CONFIDENCE" in os.environ:
            env_val = os.environ.get("NOVA_WAKE_WORD_CONFIDENCE", os.environ.get("WAKE_WORD_CONFIDENCE"))
            try:
                new_vals["wake_threshold"] = float(env_val)
            except ValueError:
                pass
        else:
            # Base: 0.50
            wake_thresh = 0.50
            
            # Noise Penalty: raise threshold in noisy environments to avoid false wakes
            noise_adjustment = noise_floor * 4.0
            wake_thresh += min(0.20, noise_adjustment)
            if noise_adjustment > 0.02:
                reasons.append(f"Raised wake threshold by +{noise_adjustment:.2f} due to high background noise ({noise_floor:.5f})")

            # Success Rate adjustment: if success rate is low (lots of false wakes), be more strict
            if success_rate < 0.70:
                wake_thresh += 0.15
                reasons.append(f"Raised wake threshold by +0.15 due to low success rate ({success_rate:.2%})")
            elif success_rate > 0.95:
                wake_thresh -= 0.05
                
            new_vals["wake_threshold"] = min(0.85, max(0.30, wake_thresh))

        # ---------------------------------------------------------
        # 2. Adapt VAD Noise Threshold (VAD_THRESHOLD)
        # ---------------------------------------------------------
        if "NOVA_VAD_THRESHOLD" in os.environ or "VAD_THRESHOLD" in os.environ:
            env_val = os.environ.get("NOVA_VAD_THRESHOLD", os.environ.get("VAD_THRESHOLD"))
            try:
                new_vals["vad_threshold"] = float(env_val)
            except ValueError:
                pass
        else:
            # Scale directly based on background noise floor
            margin = getattr(cfg, "NOISE_FLOOR_MARGIN", 0.0005)
            vad_thresh = (noise_floor * 1.5) + margin
            
            if vad_thresh > old_vals["vad_threshold"] * 1.2:
                reasons.append(f"Raised VAD threshold to {vad_thresh:.5f} to adapt to noise floor ({noise_floor:.5f})")
                
            new_vals["vad_threshold"] = min(0.01, max(0.0005, vad_thresh))

        # ---------------------------------------------------------
        # 3. Adapt Silence Timeout (SILENCE_TIMEOUT)
        # ---------------------------------------------------------
        if "NOVA_SILENCE_TIMEOUT" in os.environ or "SILENCE_TIMEOUT" in os.environ:
            env_val = os.environ.get("NOVA_SILENCE_TIMEOUT", os.environ.get("SILENCE_TIMEOUT"))
            try:
                new_vals["silence_timeout"] = float(env_val)
            except ValueError:
                pass
        else:
            silence_t = 2.0
            if noise_floor > 0.008:
                silence_t = 3.0
                reasons.append(f"Extended silence timeout to 3.0s due to noisy recording environment ({noise_floor:.5f})")
            if signal_quality_snr is not None and signal_quality_snr < 12.0:
                silence_t = max(silence_t, 3.2)
                reasons.append(f"Extended silence timeout to 3.2s due to poor signal SNR ({signal_quality_snr:.1f}dB)")
                
            new_vals["silence_timeout"] = min(4.0, max(1.5, silence_t))

        # ---------------------------------------------------------
        # 4. Adapt Speaker Verification Threshold (SPEAKER_THRESHOLD)
        # ---------------------------------------------------------
        if "NOVA_SPEAKER_THRESHOLD" in os.environ or "SPEAKER_THRESHOLD" in os.environ:
            env_val = os.environ.get("NOVA_SPEAKER_THRESHOLD", os.environ.get("SPEAKER_THRESHOLD"))
            try:
                new_vals["speaker_threshold"] = float(env_val)
            except ValueError:
                pass
        else:
            speaker_thresh = 0.75
            
            # Lower threshold slightly under poor SNR to avoid false rejections
            if signal_quality_snr is not None and signal_quality_snr < 15.0:
                speaker_thresh -= 0.05
                reasons.append(f"Lowered speaker threshold to {speaker_thresh:.2f} due to low SNR ({signal_quality_snr:.1f}dB)")
            
            # Raise threshold if success rate is low to be more strict
            if success_rate < 0.70:
                speaker_thresh += 0.05
                reasons.append(f"Raised speaker threshold to {speaker_thresh:.2f} due to low trigger success rate")
                
            new_vals["speaker_threshold"] = min(0.85, max(0.60, speaker_thresh))

        # ---------------------------------------------------------
        # Update Configuration and Log Changes
        # ---------------------------------------------------------
        has_changed = False
        for k in new_vals:
            if abs(new_vals[k] - old_vals[k]) > 1e-9:
                has_changed = True
                break

        if has_changed:
            # Set values inside cfg module
            cfg.WAKE_WORD_CONFIDENCE = new_vals["wake_threshold"]
            cfg.VAD_THRESHOLD = new_vals["vad_threshold"]
            cfg.SILENCE_TIMEOUT = new_vals["silence_timeout"]
            cfg.SPEAKER_THRESHOLD = new_vals["speaker_threshold"]
            
            self._log_adaptation_event(noise_floor, signal_quality_snr, success_rate, old_vals, new_vals, reasons)
            logger.info("Adaptive wake thresholds updated dynamically.")
            
        return new_vals

    def _log_adaptation_event(self, noise, snr, success_rate, old_v, new_v, reasons) -> None:
        event = {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "inputs": {
                "noise_floor": float(noise),
                "snr_db": float(snr) if snr is not None else None,
                "success_rate": float(success_rate)
            },
            "old_thresholds": old_v,
            "new_thresholds": new_v,
            "reasons": reasons
        }
        
        # Use non-blocking async logger (Critical optimization)
        from nova.voice.async_logging import async_log
        async_log(self.logs_path, event, 300)

