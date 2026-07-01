import sys
import os
import glob

# Auto-detect and include the project root and local .venv virtualenv site-packages
try:
    # Since this file is in nova/voice/voice_test.py, project_root is 2 levels up
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    venv_pattern = os.path.join(project_root, ".venv", "lib", "python*", "site-packages")
    venv_dirs = glob.glob(venv_pattern)
    for venv_dir in venv_dirs:
        while venv_dir in sys.path:
            try:
                sys.path.remove(venv_dir)
            except ValueError:
                break
        sys.path.append(venv_dir)
except Exception:
    pass

import io
import time
import wave
import numpy as np
import sounddevice as sd
from nova.utils import print_info, print_warning, print_error, print_success, COLOR_BOLD, COLOR_RESET

class Tee:
    def __init__(self, stream, lines_list):
        self.stream = stream
        self.lines_list = lines_list
        self.buffer = ""

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        self.buffer += data
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.lines_list.append(line)

    def flush(self):
        self.stream.flush()

def check_dependencies():
    deps = [
        "openwakeword", "onnxruntime", "sounddevice", "numpy", "scipy",
        "webrtcvad", "psutil", "resemblyzer", "faster_whisper",
    ]
    results = {}
    for dep in deps:
        try:
            mod = __import__(dep)
            results[dep] = f"PASS (v{getattr(mod, '__version__', 'installed')})"
        except ImportError as e:
            results[dep] = f"FAIL (ModuleNotFoundError: {e})"
    return results


def check_rnnoise():
    """Verify RNNoise shared library is loadable and can process a frame."""
    try:
        from nova.voice.audio_processor import RNNoiseWrapper
        rn = RNNoiseWrapper()
        if not rn.is_available():
            return "WARNING", "RNNoise library not found — denoising will be skipped."

        # Benchmark: 100 frames of 160 samples
        frame = np.random.randn(160).astype(np.float32) * 0.01
        t0 = time.time()
        for _ in range(100):
            rn.denoise_frame(frame)
        elapsed = time.time() - t0
        ms_per_frame = elapsed * 10  # 100 frames → ms each

        # Verify output dtype
        out = rn.denoise_frame(frame)
        rn.destroy()

        dtype_ok = out.dtype == np.float32
        dtype_note = "" if dtype_ok else " WARNING: output dtype is not float32"
        return "PASS", (
            f"RNNoise available | {ms_per_frame:.2f}ms/frame | "
            f"output dtype: {out.dtype}{dtype_note}"
        )
    except Exception as e:
        return "FAIL", f"RNNoise check error: {e}"


def check_agc():
    """Verify AGC does not produce clipped output."""
    try:
        from nova.voice.audio_processor import AutomaticGainControl
        agc = AutomaticGainControl()

        # Simulate quiet followed by loud signal (the most common clipping scenario)
        quiet = np.ones(480, dtype=np.float32) * 0.01
        agc.process(quiet)  # warms up gain

        loud = np.ones(480, dtype=np.float32) * 0.9
        out  = agc.process(loud)

        peak     = float(np.max(np.abs(out)))
        clipping = int(np.sum(np.abs(out) > 1.0))

        if clipping > 0:
            return "FAIL", (
                f"AGC produced {clipping} clipped samples (peak={peak:.4f}) — "
                "anti-clipping limiter missing!"
            )
        return "PASS", f"AGC anti-clipping OK | peak={peak:.4f} (no clipping)"
    except Exception as e:
        return "FAIL", f"AGC check error: {e}"


def check_audio_diagnostics():
    """Run AudioDiagnostics on a synthetic signal and verify all metrics."""
    try:
        from nova.voice.audio_processor import AudioDiagnostics
        diag = AudioDiagnostics()

        # 1 second of 440 Hz sine at 30% amplitude
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        sig = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        m = diag.measure(sig)
        required = ["rms", "peak", "noise_floor", "clipping_pct", "snr_db", "speech_dur_s"]
        missing  = [k for k in required if k not in m]
        if missing:
            return "FAIL", f"AudioDiagnostics missing keys: {missing}"

        rms  = m["rms"]
        peak = m["peak"]
        snr  = m["snr_db"]
        return "PASS", (
            f"rms={rms:.4f}  peak={peak:.4f}  "
            f"clipping={m['clipping_pct']:.2f}%  "
            f"snr={snr:.1f}dB  speech={m['speech_dur_s']:.2f}s"
        )
    except Exception as e:
        return "FAIL", f"AudioDiagnostics check error: {e}"


def check_speaker_verification():
    """Report speaker verification enrollment status."""
    try:
        from nova.voice.speaker_verify import SpeakerVerifier, _RESEMBLYZER_AVAILABLE
        from nova.voice.config import speaker_embedding_path, speaker_similarity_threshold, ENABLE_SPEAKER_CONTINUOUS_LEARNING

        if not _RESEMBLYZER_AVAILABLE:
            return "WARNING", "resemblyzer not installed — speaker verification disabled."

        verifier = SpeakerVerifier(
            embedding_path=speaker_embedding_path,
            threshold=speaker_similarity_threshold,
        )

        if not verifier.has_profile():
            return "WARNING", (
                f"No speaker profile enrolled at '{speaker_embedding_path}'.  "
                'Run "nova voice-setup" to enroll.'
            )

        meta = verifier.meta() or {}

        # 1. Enrollment samples
        enrollment_samples = meta.get("samples")
        if enrollment_samples is None:
            # Count anchors
            anchors = [item for item in meta.get("embeddings", []) if item.get("is_anchor", False)]
            if anchors:
                enrollment_samples = len(anchors)
            else:
                enrollment_samples = "Unknown"

        # 2. Total embeddings
        total_emb = verifier.total_embeddings
        max_cap = verifier.max_capacity

        # 3. Learned embeddings
        if isinstance(enrollment_samples, int):
            learned_emb = max(0, total_emb - enrollment_samples)
        else:
            learned_emb = "Unknown"

        # 4. Continuous learning
        learning_status = "Enabled" if ENABLE_SPEAKER_CONTINUOUS_LEARNING else "Disabled"

        # 5. Last updated
        last_updated = meta.get("updated_at")
        if not last_updated:
            last_updated = meta.get("enrolled_at", "Unknown")

        # Optional diagnostics (display if they exist in metadata)
        optional_lines = []
        for key, label in [
            ("rejected_duplicates", "Rejected duplicates"),
            ("rejected_low_quality", "Rejected low-quality samples"),
            ("rejected_drift", "Rejected drift samples")
        ]:
            if key in meta:
                optional_lines.append(f"    {label:<21} : {meta[key]}")

        optional_str = "\n" + "\n".join(optional_lines) if optional_lines else ""

        msg = (
            f"    Enrollment samples   : {enrollment_samples}\n"
            f"    Learned embeddings   : {learned_emb}\n"
            f"    Total embeddings     : {total_emb} / {max_cap}\n"
            f"    Threshold            : {speaker_similarity_threshold}\n"
            f"    Continuous learning  : {learning_status}\n"
            f"    Last updated         : {last_updated}"
            f"{optional_str}"
        )
        return "PASS", msg
    except Exception as e:
        return "FAIL", f"Speaker verification check error: {e}"

def check_microphone():
    try:
        device_info = sd.query_devices(kind='input')
        if not device_info:
            return "FAIL", "No input device detected."
        
        name = device_info.get("name")
        sr = device_info.get("default_samplerate")
        ch = device_info.get("max_input_channels")
        
        # Test opening input stream
        with sd.InputStream(samplerate=16000, channels=1, dtype='float32') as stream:
            pass
            
        return "PASS", f"Detected: '{name}' | Default SR: {sr}Hz | Input Channels: {ch}"
    except Exception as e:
        return "FAIL", f"Microphone error: {e}"

def check_model():
    try:
        import openwakeword
        package_dir = os.path.dirname(openwakeword.__file__)
        resources_model_path = os.path.join(package_dir, "resources", "models", "hey_nova_v0.1.onnx")
        if not os.path.exists(resources_model_path):
            return "FAIL", f"hey_nova_v0.1.onnx not found at resource path: {resources_model_path}"
        
        # Verify model loads
        from openwakeword.model import Model
        model = Model(wakeword_model_paths=[resources_model_path])
        return "PASS", f"Path resolved & loaded successfully:\n{resources_model_path}"
    except Exception as e:
        return "FAIL", f"Model loading failure: {e}"

def check_inference():
    try:
        import openwakeword
        from openwakeword.model import Model
        package_dir = os.path.dirname(openwakeword.__file__)
        model_path = os.path.join(package_dir, "resources", "models", "hey_nova_v0.1.onnx")
        
        model = Model(wakeword_model_paths=[model_path])
        model_name = os.path.splitext(os.path.basename(model_path))[0]
        
        # 1280 samples of silent 16-bit PCM
        dummy_pcm = np.zeros(1280, dtype=np.int16)
        predictions = model.predict(dummy_pcm)
        
        if model_name not in predictions:
            return "FAIL", f"Model name key '{model_name}' not found in predictions dictionary: {predictions}"
            
        score = predictions.get(model_name, 0.0)
        return "PASS", f"Inference completed. Score: {score} | Predictions: {predictions}"
    except Exception as e:
        return "FAIL", f"Inference check error: {e}"

def check_wake_word_signal():
    try:
        sample_rate = 16000
        channels = 1
        duration = 2.0
        
        print_info(f"🎤 Recording a {duration}-second audio clip to verify live microphone signal. Please speak...")
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=channels, dtype='float32')
        sd.wait()
        
        # Calculate Root Mean Square (RMS)
        rms = float(np.sqrt(np.mean(np.square(recording))))
        
        details = (
            f"Frame size: {len(recording)} | "
            f"Sample rate: {sample_rate}Hz | "
            f"Channels: {channels} | "
            f"Dtype: {recording.dtype} | "
            f"RMS Amplitude: {rms:.6f}"
        )
        
        if rms == 0.0:
            return "FAIL", f"Captured audio is completely silent (RMS = 0). Check if mic is muted. Details: {details}"
            
        return "PASS", f"Audio signal verified successfully. Details: {details}"
    except Exception as e:
        return "FAIL", f"Signal check failure: {e}"

def check_stt_connectivity():
    try:
        from nova.voice.stt import get_stt_provider, WhisperSTTProvider
        stt_provider = get_stt_provider()
        
        # Generate 1-second of mock silence audio bytes
        sample_rate = 16000
        channels = 1
        duration = 1.0
        dummy_pcm = np.zeros(int(duration * sample_rate), dtype=np.int16)
        
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(dummy_pcm.tobytes())
        wav_bytes = wav_io.getvalue()
        
        provider_name = "Whisper (Local)" if isinstance(stt_provider, WhisperSTTProvider) else "Nebius"
        print_info(f"📤 Sending silent query to {provider_name} STT to verify pipeline...")
        transcription = stt_provider.transcribe(wav_bytes, silent=True)
        return "PASS", f"({provider_name}) Transcription returned: '{transcription}'"
    except Exception as e:
        return "FAIL", f"STT pipeline check failure: {e}"

def main():
    import re
    import platform
    from nova.voice.config import DIAGNOSTICS_LOG_PATH

    log_lines = []
    original_stdout = sys.stdout
    sys.stdout = Tee(original_stdout, log_lines)

    overall_pass = True
    
    try:
        print(f"\n{COLOR_BOLD}=== NOVA VOICE SUBSYSTEM SELF-TEST ==={COLOR_RESET}\n")
        
        # 1. Dependency Check
        print_info("Checking python module dependencies...")
        dep_results = check_dependencies()
        dep_all_pass = True
        for dep, status in dep_results.items():
            if "FAIL" in status:
                dep_all_pass = False
                print_error(f"  - {dep}: {status}")
            else:
                print_success(f"  - {dep}: {status}")
                
        print(f"✓ Dependency Check: {'PASS' if dep_all_pass else 'FAIL'}")
        if not dep_all_pass:
            overall_pass = False
        print("-" * 50)
        
        # 2. Microphone Check
        print_info("Checking microphone device accessibility...")
        mic_status, mic_msg = check_microphone()
        if mic_status == "FAIL":
            overall_pass = False
            print_error(f"  - {mic_msg}")
        else:
            print_success(f"  - {mic_msg}")
        print(f"✓ Microphone Check: {mic_status}")
        print("-" * 50)
        
        # 3. Model Check
        print_info("Checking wake-word model existence and loading...")
        model_status, model_msg = check_model()
        if model_status == "FAIL":
            overall_pass = False
            print_error(f"  - {model_msg}")
        else:
            print_success(f"  - {model_msg}")
        print(f"✓ Model Check: {model_status}")
        print("-" * 50)
        
        # 4. Inference Check
        print_info("Running dummy audio inference on OpenWakeWord...")
        inf_status, inf_msg = check_inference()
        if inf_status == "FAIL":
            overall_pass = False
            print_error(f"  - {inf_msg}")
        else:
            print_success(f"  - {inf_msg}")
        print(f"✓ Inference Check: {inf_status}")
        print("-" * 50)
        
        # 5. Signal Check
        print_info("Testing live audio signal capture...")
        sig_status, sig_msg = check_wake_word_signal()
        if sig_status == "FAIL":
            overall_pass = False
            print_error(f"  - {sig_msg}")
        else:
            print_success(f"  - {sig_msg}")
        print(f"✓ Wake-Word Signal Check: {sig_status}")
        print("-" * 50)
        
        # 6. STT Connection Check
        print_info("Verifying STT pipeline...")
        stt_status, stt_msg = check_stt_connectivity()
        if stt_status == "FAIL":
            overall_pass = False
            print_error(f"  - {stt_msg}")
        else:
            print_success(f"  - {stt_msg}")
        print(f"✓ STT Check: {stt_status}")
        print("-" * 50)

        # 7. RNNoise Check
        print_info("Verifying RNNoise denoiser...")
        rn_status, rn_msg = check_rnnoise()
        if rn_status == "FAIL":
            overall_pass = False
            print_error(f"  - {rn_msg}")
        elif rn_status == "WARNING":
            print_warning(f"  - {rn_msg}")
        else:
            print_success(f"  - {rn_msg}")
        print(f"✓ RNNoise Check: {rn_status}")
        print("-" * 50)

        # 8. AGC Anti-Clipping Check
        print_info("Verifying AGC anti-clipping limiter...")
        agc_status, agc_msg = check_agc()
        if agc_status == "FAIL":
            overall_pass = False
            print_error(f"  - {agc_msg}")
        else:
            print_success(f"  - {agc_msg}")
        print(f"✓ AGC Check: {agc_status}")
        print("-" * 50)

        # 9. Audio Diagnostics Check
        print_info("Verifying AudioDiagnostics metrics...")
        diag_status, diag_msg = check_audio_diagnostics()
        if diag_status == "FAIL":
            overall_pass = False
            print_error(f"  - {diag_msg}")
        else:
            print_success(f"  - {diag_msg}")
        print(f"✓ AudioDiagnostics Check: {diag_status}")
        print("-" * 50)

        # 10. Speaker Verification Status
        print_info("Checking speaker verification enrollment...")
        sv_status, sv_msg = check_speaker_verification()
        if sv_status == "FAIL":
            overall_pass = False
            print_error(f"  - {sv_msg}")
        elif sv_status == "WARNING":
            print_warning(f"  - {sv_msg}")
        else:
            print_success("Speaker profile enrolled\n")
            print(sv_msg)
        print(f"✓ Speaker Verification: {sv_status}")
        print("=" * 50)
        
        # Print final summary
        print(f"\n{COLOR_BOLD}=== FINAL SELF-TEST SUMMARY ==={COLOR_RESET}\n")
        print(f"  dependency check:          {'PASS' if dep_all_pass else 'FAIL'}")
        print(f"  microphone check:          {mic_status}")
        print(f"  model check:               {model_status}")
        print(f"  inference check:           {inf_status}")
        print(f"  wake-word signal:          {sig_status}")
        print(f"  STT check:                 {stt_status}")
        print(f"  RNNoise check:             {rn_status}")
        print(f"  AGC anti-clipping:         {agc_status}")
        print(f"  audio diagnostics:         {diag_status}")
        print(f"  speaker verification:      {sv_status}")
        
        print("\n" + "=" * 50)
        if overall_pass:
            print_success("OVERALL STATUS: PASS")
            exit_code = 0
        else:
            print_error("OVERALL STATUS: FAIL")
            exit_code = 1
    finally:
        sys.stdout = original_stdout
        # Write log to file
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            sys_info = (
                f"Nova Voice Diagnostics Log\n"
                f"Timestamp: {timestamp}\n"
                f"OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
                f"Python: {platform.python_version()}\n"
                f"==================================================\n\n"
            )
            # Remove ANSI colors for log readability
            clean_lines = [re.sub(r'\x1b\[[0-9;]*m', '', line) for line in log_lines]
            log_content = sys_info + "\n".join(clean_lines) + "\n"
            os.makedirs(os.path.dirname(DIAGNOSTICS_LOG_PATH), exist_ok=True)
            with open(DIAGNOSTICS_LOG_PATH, "w") as f:
                f.write(log_content)
            print_success(f"Diagnostics log saved to: {DIAGNOSTICS_LOG_PATH}")
        except Exception as e:
            print_warning(f"Failed to save diagnostics log: {e}")
            
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
