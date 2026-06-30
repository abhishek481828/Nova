"""
Audio Quality Analysis module for Nova.

Provides estimators for Signal-to-Noise Ratio (SNR), background noise floor,
microphone clipping, voice volume, and echo levels, producing a unified
audio quality score in [0.0, 1.0].
"""

import numpy as np
from nova.logger import logger

class AudioQualityAnalyzer:
    def __init__(self, sample_rate: int = 16000, frame_size: int = 480):
        self.sample_rate = sample_rate
        self.frame_size = frame_size

    def analyze(self, audio: np.ndarray, ref_audio: np.ndarray | None = None) -> dict[str, float]:
        """
        Analyze audio and estimate quality metrics.
        
        Args:
            audio: 1D float32 numpy array representing the microphone signal.
            ref_audio: Optional 1D float32 numpy array representing the reference playback signal.
            
        Returns:
            Dict containing estimated metrics:
              - snr_db: Signal-to-noise ratio in dB
              - background_noise: Background noise floor (RMS)
              - clipping_pct: Percentage of clipped samples
              - voice_volume: Active voice volume (RMS)
              - echo_level: Estimated echo level in [0.0, 1.0]
              - overall_quality: Overall quality score in [0.0, 1.0]
        """
        flat = audio.flatten().astype(np.float32)
        if len(flat) == 0:
            return {
                "snr_db": 0.0,
                "background_noise": 0.0,
                "clipping_pct": 0.0,
                "voice_volume": 0.0,
                "echo_level": 0.0,
                "overall_quality": 0.0
            }

        # 1. Background Noise & SNR
        n_frames = len(flat) // self.frame_size
        frame_rms = []
        for i in range(max(1, n_frames)):
            start = i * self.frame_size
            end = min(len(flat), start + self.frame_size)
            frame = flat[start:end]
            if len(frame) > 0:
                frame_rms.append(float(np.sqrt(np.mean(frame * frame))))
        
        frame_rms.sort()
        
        # Estimate background noise floor as the mean of the quietest 10% of frames
        n_quietest = max(1, len(frame_rms) // 10)
        background_noise = float(np.mean(frame_rms[:n_quietest]))
        
        # Estimate signal level as the mean of the loudest 30% of frames
        n_loudest = max(1, int(len(frame_rms) * 0.3))
        signal_rms = float(np.mean(frame_rms[-n_loudest:]))
        
        if background_noise > 1e-9:
            snr_db = float(20.0 * np.log10(signal_rms / background_noise))
            if snr_db < 0.0:
                snr_db = 0.0
        else:
            snr_db = 100.0

        # 2. Microphone Clipping
        clipping_count = int(np.sum(np.abs(flat) >= 0.99))
        clipping_pct = float((clipping_count / len(flat)) * 100.0)

        # 3. Voice Volume (RMS of active speech frames)
        speech_frames = [r for r in frame_rms if r > background_noise * 1.8]
        if speech_frames:
            voice_volume = float(np.mean(speech_frames))
        else:
            voice_volume = float(np.mean(frame_rms))

        # 4. Echo Level
        echo_level = 0.0
        if ref_audio is not None and len(ref_audio) > 0:
            ref_flat = ref_audio.flatten().astype(np.float32)
            # Match lengths for correlation
            min_len = min(len(flat), len(ref_flat))
            if min_len > 10:
                s1 = flat[:min_len]
                s2 = ref_flat[:min_len]
                
                norm1 = np.linalg.norm(s1)
                norm2 = np.linalg.norm(s2)
                
                if norm1 > 1e-6 and norm2 > 1e-6:
                    # Calculate cross-correlation coefficient
                    corr = np.abs(np.dot(s1, s2)) / (norm1 * norm2)
                    echo_level = float(min(1.0, max(0.0, corr)))

        # 5. Overall Quality Score
        # SNR score: 0 at 5dB, 1 at 25dB
        snr_score = min(1.0, max(0.0, (snr_db - 5.0) / 20.0))
        # Clipping penalty: 1% clipping completely ruins quality
        clipping_penalty = min(1.0, clipping_pct / 1.0)
        # Noise penalty: 0.1 RMS noise is a 100% penalty
        noise_penalty = min(1.0, background_noise * 10.0)
        # Volume score: penalize too quiet
        volume_score = 1.0
        if voice_volume < 0.005:
            volume_score = float(max(0.0, voice_volume / 0.005))
        # Echo penalty: 0.6 correlation is 100% penalty
        echo_penalty = min(1.0, echo_level * 1.67)

        overall = (snr_score * 0.4 + (1.0 - noise_penalty) * 0.3 + volume_score * 0.3) * (1.0 - clipping_penalty) * (1.0 - echo_penalty)
        overall_quality = float(min(1.0, max(0.0, overall)))

        return {
            "snr_db": snr_db,
            "background_noise": background_noise,
            "clipping_pct": clipping_pct,
            "voice_volume": voice_volume,
            "echo_level": echo_level,
            "overall_quality": overall_quality
        }
