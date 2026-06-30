"""
Voice Diagnostics Engine for Nova.

Single collector for all voice pipeline events. Tracks:
  - Wake-word successes, false wakes, missed wakes
  - End-to-end, STT, and TTS latency per turn
  - Audio quality snapshots (SNR, noise, clipping, echo)
  - Ambient noise history
  - Speaker verification confidence history
  - CPU and memory usage of the Nova process

Public API
----------
record_wake_success(score, latency_ms)
record_false_wake(score, noise_floor)
record_missed_wake(score, noise_floor)
record_turn(latency_ms, stt_latency_ms, tts_latency_ms,
            audio_quality, speaker_confidence, noise_floor)
record_audio_quality(metrics: dict)
record_noise_sample(rms: float)

get_wake_stats()      -> dict
get_latency_stats()   -> dict
get_audio_quality_stats() -> dict
get_noise_history(n)  -> list[float]
get_speaker_confidence_stats() -> dict
get_resource_usage()  -> dict

generate_report(fmt="text"|"json") -> str
save_report(path=None) -> str   # returns path written
"""

import os
import json
import time
import threading
import collections
from typing import Optional
from nova.logger import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def _percentile(data: list[float], p: float) -> float:
    """Compute the p-th percentile (0–100) of a sorted copy of data."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _safe_mean(seq) -> float:
    lst = list(seq)
    return sum(lst) / len(lst) if lst else 0.0


def _safe_min(seq) -> float:
    lst = list(seq)
    return min(lst) if lst else 0.0


def _safe_max(seq) -> float:
    lst = list(seq)
    return max(lst) if lst else 0.0


# ---------------------------------------------------------------------------
# VoiceDiagnosticsEngine
# ---------------------------------------------------------------------------

_MAX_HISTORY = 500   # cap in-memory deques to prevent unbounded growth


class VoiceDiagnosticsEngine:
    """
    Thread-safe diagnostics collector for Nova's voice pipeline.

    Designed to be instantiated once per daemon lifetime and referenced
    through ``voice_config.active_diagnostics``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # ── Wake tracking ──────────────────────────────────────────────────
        self._wake_successes: collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)
        self._false_wakes:    collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)
        self._missed_wakes:   collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)

        # ── Turn latency tracking ──────────────────────────────────────────
        self._turns: collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)

        # ── Audio quality snapshots ────────────────────────────────────────
        self._quality_snapshots: collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)

        # ── Ambient noise history (RMS samples) ───────────────────────────
        self._noise_history: collections.deque[float] = collections.deque(maxlen=_MAX_HISTORY)

        # ── Speaker confidence per turn ────────────────────────────────────
        self._speaker_confidence: collections.deque[float] = collections.deque(maxlen=_MAX_HISTORY)

        # ── Diagnostics output path ────────────────────────────────────────
        self._diag_path = os.path.expanduser("~/.config/nova/voice_diagnostics.json")
        os.makedirs(os.path.dirname(self._diag_path), exist_ok=True)

        # ── Session start ──────────────────────────────────────────────────
        self._session_start = time.time()

    # ── Write API ──────────────────────────────────────────────────────────

    def record_wake_success(self, score: float, latency_ms: float) -> None:
        """Record a wake-word event that passed the fusion engine threshold."""
        with self._lock:
            self._wake_successes.append({
                "ts": time.time(),
                "score": float(score),
                "latency_ms": float(latency_ms),
            })

    def record_false_wake(self, score: float, noise_floor: float) -> None:
        """Record a wake trigger rejected by the confidence fusion engine."""
        with self._lock:
            self._false_wakes.append({
                "ts": time.time(),
                "score": float(score),
                "noise_floor": float(noise_floor),
            })

    def record_missed_wake(self, score: float, noise_floor: float) -> None:
        """Record a near-miss wake (score below threshold but above a lower bound)."""
        with self._lock:
            self._missed_wakes.append({
                "ts": time.time(),
                "score": float(score),
                "noise_floor": float(noise_floor),
            })

    def record_turn(
        self,
        latency_ms: float,
        stt_latency_ms: float = 0.0,
        tts_latency_ms: float = 0.0,
        audio_quality: float = 1.0,
        speaker_confidence: Optional[float] = None,
        noise_floor: float = 0.0,
    ) -> None:
        """Record a complete voice interaction turn."""
        with self._lock:
            self._turns.append({
                "ts": time.time(),
                "latency_ms": float(latency_ms),
                "stt_latency_ms": float(stt_latency_ms),
                "tts_latency_ms": float(tts_latency_ms),
                "audio_quality": float(audio_quality),
                "noise_floor": float(noise_floor),
            })
            if speaker_confidence is not None:
                self._speaker_confidence.append(float(speaker_confidence))

    def record_audio_quality(self, metrics: dict) -> None:
        """Record a snapshot from AudioQualityAnalyzer.analyze()."""
        with self._lock:
            self._quality_snapshots.append({
                "ts": time.time(),
                **{k: float(v) for k, v in metrics.items()},
            })

    def record_noise_sample(self, rms: float) -> None:
        """Record a single ambient noise RMS sample."""
        with self._lock:
            self._noise_history.append(float(rms))

    # ── Read API ───────────────────────────────────────────────────────────

    def get_wake_stats(self) -> dict:
        """Return aggregated wake-word statistics."""
        with self._lock:
            n_success = len(self._wake_successes)
            n_false   = len(self._false_wakes)
            n_missed  = len(self._missed_wakes)
            total     = n_success + n_false
            rate      = (n_success / total) if total > 0 else 0.0

            latencies = [e["latency_ms"] for e in self._wake_successes]
            scores    = [e["score"]      for e in self._wake_successes]

        return {
            "success_count":   n_success,
            "false_wake_count": n_false,
            "missed_wake_count": n_missed,
            "total_triggers":  total,
            "success_rate":    round(rate, 4),
            "avg_wake_latency_ms": round(_safe_mean(latencies), 2),
            "avg_wake_score":  round(_safe_mean(scores), 4),
        }

    def get_latency_stats(self) -> dict:
        """Return aggregated latency statistics across all turns."""
        with self._lock:
            e2e  = [t["latency_ms"]     for t in self._turns]
            stt  = [t["stt_latency_ms"] for t in self._turns]
            tts  = [t["tts_latency_ms"] for t in self._turns]

        def _stats(data: list[float], label: str) -> dict:
            return {
                f"{label}_avg_ms":  round(_safe_mean(data), 2),
                f"{label}_min_ms":  round(_safe_min(data), 2),
                f"{label}_max_ms":  round(_safe_max(data), 2),
                f"{label}_p95_ms":  round(_percentile(data, 95), 2),
            }

        result = {"turn_count": len(e2e)}
        result.update(_stats(e2e, "e2e"))
        result.update(_stats(stt, "stt"))
        result.update(_stats(tts, "tts"))
        return result

    def get_audio_quality_stats(self) -> dict:
        """Return averaged audio quality metrics across all snapshots."""
        with self._lock:
            snaps = list(self._quality_snapshots)

        if not snaps:
            return {
                "snapshot_count": 0,
                "avg_snr_db": 0.0,
                "avg_background_noise": 0.0,
                "avg_clipping_pct": 0.0,
                "avg_voice_volume": 0.0,
                "avg_echo_level": 0.0,
                "avg_overall_quality": 0.0,
            }

        keys = ["snr_db", "background_noise", "clipping_pct",
                "voice_volume", "echo_level", "overall_quality"]
        out = {"snapshot_count": len(snaps)}
        for k in keys:
            vals = [s[k] for s in snaps if k in s]
            out[f"avg_{k}"] = round(_safe_mean(vals), 4)
        return out

    def get_noise_history(self, n: int = 50) -> list[float]:
        """Return the last N ambient noise RMS samples."""
        with self._lock:
            history = list(self._noise_history)
        return history[-n:]

    def get_speaker_confidence_stats(self) -> dict:
        """Return speaker verification confidence statistics."""
        with self._lock:
            conf = list(self._speaker_confidence)

        if not conf:
            return {"sample_count": 0, "avg": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0}

        return {
            "sample_count": len(conf),
            "avg":  round(_safe_mean(conf), 4),
            "min":  round(_safe_min(conf), 4),
            "max":  round(_safe_max(conf), 4),
            "p95":  round(_percentile(conf, 95), 4),
        }

    def get_resource_usage(self) -> dict:
        """Return current CPU%, RSS memory MB, and thread count of this process."""
        try:
            import psutil, os as _os
            proc = psutil.Process(_os.getpid())
            return {
                "cpu_pct":      round(proc.cpu_percent(interval=0.1), 1),
                "memory_mb":    round(proc.memory_info().rss / 1_048_576, 1),
                "thread_count": proc.num_threads(),
            }
        except ImportError:
            # psutil unavailable — report via /proc/self/status
            try:
                import resource as _res
                usage = _res.getrusage(_res.RUSAGE_SELF)
                kb = usage.ru_maxrss   # KB on Linux
                return {
                    "cpu_pct": None,
                    "memory_mb": round(kb / 1024.0, 1),
                    "thread_count": None,
                }
            except Exception:
                return {"cpu_pct": None, "memory_mb": None, "thread_count": None}
        except Exception as e:
            logger.debug(f"Resource usage query failed: {e}")
            return {"cpu_pct": None, "memory_mb": None, "thread_count": None}

    # ── Report API ─────────────────────────────────────────────────────────

    def generate_report(self, fmt: str = "text") -> str:
        """
        Generate a diagnostics report.

        Parameters
        ----------
        fmt : "text" | "json"

        Returns
        -------
        str  — formatted report string
        """
        wake    = self.get_wake_stats()
        latency = self.get_latency_stats()
        quality = self.get_audio_quality_stats()
        speaker = self.get_speaker_confidence_stats()
        noise   = self.get_noise_history(n=50)
        res     = self.get_resource_usage()

        uptime_s = time.time() - self._session_start

        if fmt == "json":
            report = {
                "generated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "session_uptime_s": round(uptime_s, 1),
                "wake":           wake,
                "latency":        latency,
                "audio_quality":  quality,
                "speaker":        speaker,
                "noise_history":  [round(v, 5) for v in noise],
                "resource_usage": res,
            }
            return json.dumps(report, indent=2)

        # ── Text report ────────────────────────────────────────────────────
        lines = [
            "╔══════════════════════════════════════════════════════╗",
            "║         Nova Voice Diagnostics Report                ║",
            "╚══════════════════════════════════════════════════════╝",
            f"  Generated : {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Uptime    : {int(uptime_s // 60)}m {int(uptime_s % 60)}s",
            "",
            "── Wake-Word ─────────────────────────────────────────",
            f"  Successes     : {wake['success_count']}",
            f"  False wakes   : {wake['false_wake_count']}",
            f"  Missed wakes  : {wake['missed_wake_count']}",
            f"  Success rate  : {_pct(wake['success_rate'])}",
            f"  Avg score     : {wake['avg_wake_score']:.4f}",
            f"  Avg latency   : {wake['avg_wake_latency_ms']:.1f} ms",
            "",
            "── Latency ───────────────────────────────────────────",
            f"  Turns logged  : {latency['turn_count']}",
            f"  E2E avg/p95   : {latency['e2e_avg_ms']:.0f} ms / {latency['e2e_p95_ms']:.0f} ms",
            f"  STT avg/p95   : {latency['stt_avg_ms']:.0f} ms / {latency['stt_p95_ms']:.0f} ms",
            f"  TTS avg/p95   : {latency['tts_avg_ms']:.0f} ms / {latency['tts_p95_ms']:.0f} ms",
            "",
            "── Audio Quality ─────────────────────────────────────",
            f"  Snapshots     : {quality['snapshot_count']}",
            f"  Avg SNR       : {quality['avg_snr_db']:.1f} dB",
            f"  Avg noise RMS : {quality['avg_background_noise']:.5f}",
            f"  Avg clipping  : {quality['avg_clipping_pct']:.2f}%",
            f"  Avg echo lvl  : {quality['avg_echo_level']:.4f}",
            f"  Avg quality   : {quality['avg_overall_quality']:.3f} / 1.000",
            "",
            "── Speaker Confidence ────────────────────────────────",
            f"  Samples       : {speaker['sample_count']}",
            f"  Avg / p95     : {speaker['avg']:.4f} / {speaker['p95']:.4f}",
            f"  Min / Max     : {speaker['min']:.4f} / {speaker['max']:.4f}",
            "",
            "── Ambient Noise (last 10 samples) ───────────────────",
        ]
        noise_tail = noise[-10:]
        if noise_tail:
            bar_line = "  " + "  ".join(
                f"{v:.4f}" for v in noise_tail
            )
            lines.append(bar_line)
        else:
            lines.append("  (no samples yet)")
        lines.append("")
        lines += [
            "── Resource Usage ────────────────────────────────────",
            f"  CPU           : {res['cpu_pct']}%",
            f"  Memory (RSS)  : {res['memory_mb']} MB",
            f"  Threads       : {res['thread_count']}",
            "",
            "══════════════════════════════════════════════════════",
        ]
        return "\n".join(lines)

    def save_report(self, path: Optional[str] = None) -> str:
        """
        Save a text diagnostics report to disk.

        Returns the path written.
        """
        if path is None:
            path = os.path.expanduser("~/.config/nova/diagnostics_report.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        report = self.generate_report(fmt="text")
        with open(path, "w") as f:
            f.write(report)
        logger.info(f"Diagnostics report saved: {path}")
        return path

    def flush_to_disk(self) -> None:
        """Persist current in-memory stats to voice_diagnostics.json."""
        try:
            payload = {
                "flushed_at": time.time(),
                "wake":    self.get_wake_stats(),
                "latency": self.get_latency_stats(),
                "quality": self.get_audio_quality_stats(),
                "speaker": self.get_speaker_confidence_stats(),
            }
            with open(self._diag_path, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.debug(f"Diagnostics flush failed: {e}")
