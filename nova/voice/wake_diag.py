"""
Wake-word diagnostic — records 4 seconds then runs the clip through
OpenWakeWord at multiple gain levels to find the optimal setting.

Usage:  nova wake-diag
"""
import sys, os, time, wave
import numpy as np
import sounddevice as sd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from nova.voice.config import SAMPLE_RATE, CHANNELS, WAKE_WORD_MODEL_PATH
from nova.utils import print_info, print_success, print_warning, print_error


def main():
    print_info("=== Wake-Word Diagnostic ===\n")

    # ── 1. Audio device info ──
    print_info("[1/4] Audio Devices")
    try:
        devices = sd.query_devices()
        default_in = sd.query_devices(kind="input")
        print(f"  Default input: {default_in['name']}")
        print(f"  Sample rate:   {default_in['default_samplerate']} Hz")
        print(f"  Max channels:  {default_in['max_input_channels']}")
        print()
        print("  All input devices:")
        for i in range(len(devices)):
            d = devices[i]
            if d['max_input_channels'] > 0:
                marker = " ◀ DEFAULT" if d["name"] == default_in["name"] else ""
                print(f"    [{i}] {d['name']}  (ch={d['max_input_channels']}, sr={d['default_samplerate']}){marker}")
        print()
    except Exception as e:
        print_error(f"  Device query failed: {e}\n")

    # ── 2. Record 4 seconds ──
    duration = 4.0
    print_info(f"[2/4] Say 'Hey Nova' NOW (recording {duration}s)...")
    try:
        recording = sd.rec(
            int(SAMPLE_RATE * duration),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocking=True,
        )
        print_success("  Recording complete\n")
    except Exception as e:
        print_error(f"  Recording failed: {e}")
        return

    flat = recording.flatten()

    # ── 3. Signal analysis ──
    print_info("[3/4] Signal Analysis")
    rms = float(np.sqrt(np.mean(flat * flat)))
    peak = float(np.max(np.abs(flat)))
    print(f"  RMS:         {rms:.5f}")
    print(f"  Peak:        {peak:.5f}")
    print(f"  Int16 peak:  {int(peak * 32767)} / 32767")

    if peak < 0.01:
        print_error("  ✘ No signal — mic appears dead!\n")
        return
    elif peak > 0.95:
        print_warning("  ⚠ Audio is CLIPPING — reduce mic gain\n")
    elif peak < 0.1:
        print_warning("  ⚠ Very quiet signal\n")
    else:
        print_success("  Signal OK\n")

    # ── 4. Run OWW at multiple gain levels ──
    print_info("[4/4] Testing OpenWakeWord at multiple gain levels...\n")

    try:
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        from openwakeword.model import Model
        model_name = os.path.splitext(os.path.basename(WAKE_WORD_MODEL_PATH))[0]

        # Test at different software gain multipliers
        gains = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]
        best_score = 0
        best_gain = 1.0

        print(f"  {'Gain':>5}  {'Peak':>7}  {'MaxScore':>9}  {'Result'}")
        print(f"  {'─'*5}  {'─'*7}  {'─'*9}  {'─'*20}")

        for gain in gains:
            amplified = flat * gain
            amp_peak = float(np.max(np.abs(amplified)))
            clipped = amp_peak > 1.0

            # Clip and convert to int16
            pcm = (np.clip(amplified, -1.0, 1.0) * 32767).astype(np.int16)

            # Fresh model instance for each gain to reset internal buffers
            model = Model(wakeword_model_paths=[WAKE_WORD_MODEL_PATH])
            results = model.predict_clip(pcm, padding=0)

            if results:
                scores = [r.get(model_name, 0.0) for r in results]
                max_score = max(scores)
            else:
                max_score = 0.0

            status = ""
            if clipped:
                status = "⚠ clipping"
            elif max_score >= 0.5:
                status = "✔ STRONG"
            elif max_score >= 0.3:
                status = "✔ DETECTED"
            elif max_score >= 0.1:
                status = "~ weak"
            else:
                status = "✘ not detected"

            bar = "█" * int(max_score * 40)
            print(f"  {gain:>5.1f}x  {min(amp_peak,1.0):>6.3f}  {max_score:>8.4f}  {status}  {bar}")

            if max_score > best_score and not clipped:
                best_score = max_score
                best_gain = gain

        print()

        if best_score >= 0.3:
            print_success(f"  ✔ Best: gain={best_gain}x → score={best_score:.4f}")
            if best_gain != 1.0:
                print_info(f"    Recommended: apply {best_gain}x software gain in the wake loop")
                # Calculate recommended wpctl volume
                try:
                    import subprocess
                    result = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"],
                                          capture_output=True, text=True)
                    current = float(result.stdout.strip().split()[-1])
                    recommended = min(current * best_gain, 1.0)
                    print_info(f"    OR set mic volume: wpctl set-volume @DEFAULT_AUDIO_SOURCE@ {recommended:.2f}")
                except Exception:
                    pass
            print()
        elif best_score >= 0.1:
            print_warning(f"  ⚠ Best: gain={best_gain}x → score={best_score:.4f}")
            print_warning("    Detection possible but unreliable. Try speaking louder/closer.\n")
        else:
            print_error(f"  ✘ Cannot detect 'Hey Nova' at any gain (best={best_score:.4f})")
            print_error("    Check microphone device and positioning.\n")

    except Exception as e:
        print_error(f"  Failed: {e}\n")
        import traceback
        traceback.print_exc()

    # ── Save WAV ──
    save_path = os.path.expanduser("~/.config/nova/wake_diag.wav")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    try:
        pcm_save = (np.clip(flat, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(save_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_save.tobytes())
        print_info(f"  Recording saved: {save_path}")
        print_info(f"  Play it:  aplay {save_path}\n")
    except Exception as e:
        print_error(f"  Save failed: {e}\n")


if __name__ == "__main__":
    main()
