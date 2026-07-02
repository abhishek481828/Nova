import os
import sys
import io
import wave
import numpy as np
import sounddevice as sd

from nova.voice.config import (
    SAMPLE_RATE, speaker_embedding_path, speaker_similarity_threshold,
)
from nova.utils import (
    print_info, print_warning, print_error, print_success,
    COLOR_BOLD, COLOR_RESET
)
from nova.voice.speaker import SpeakerVerifier
from nova.voice.whisper import get_stt_provider
from nova.voice.pipeline.processors import (
    RNNoiseWrapper, AutomaticGainControl, AudioDiagnostics
)

def run_voice_self_test() -> None:
    overall_pass = True

    print(f"\n{COLOR_BOLD}=== NOVA VOICE SUBSYSTEM SELF-TEST ==={COLOR_RESET}\n")

    # 1. Dependency Check
    print_info("Checking python module dependencies...")
    deps = [
        "openwakeword", "onnxruntime", "sounddevice", "numpy", "scipy",
        "webrtcvad", "psutil", "resemblyzer", "faster_whisper",
    ]
    dep_all_pass = True
    for dep in deps:
        try:
            mod = __import__(dep)
            print_success(f"  - {dep}: PASS (v{getattr(mod, '__version__', 'installed')})")
        except ImportError as e:
            dep_all_pass = False
            print_error(f"  - {dep}: FAIL (ModuleNotFoundError: {e})")

    print(f"✓ Dependency Check: {'PASS' if dep_all_pass else 'FAIL'}")
    if not dep_all_pass:
        overall_pass = False
    print("-" * 50)

    # 2. Microphone Check
    print_info("Checking microphone device accessibility...")
    try:
        device_info = sd.query_devices(kind='input')
        if not device_info:
            mic_status, mic_msg = "FAIL", "No input device detected."
        else:
            name = device_info.get("name")
            sr = device_info.get("default_samplerate")
            ch = device_info.get("max_input_channels")
            with sd.InputStream(samplerate=16000, channels=1, dtype='float32') as stream:
                pass
            mic_status, mic_msg = "PASS", f"Detected: '{name}' | Default SR: {sr}Hz | Input Channels: {ch}"
    except Exception as e:
        mic_status, mic_msg = "FAIL", f"Microphone error: {e}"

    if mic_status == "FAIL":
        overall_pass = False
        print_error(f"  - {mic_msg}")
    else:
        print_success(f"  - {mic_msg}")
    print(f"✓ Microphone Check: {mic_status}")
    print("-" * 50)

    # 3. Model Check
    print_info("Checking wake-word model existence and loading...")
    try:
        import openwakeword
        package_dir = os.path.dirname(openwakeword.__file__)
        resources_model_path = os.path.join(package_dir, "resources", "models", "hey_nova_v0.1.onnx")
        if not os.path.exists(resources_model_path):
            model_status, model_msg = "FAIL", f"hey_nova_v0.1.onnx not found at resource path: {resources_model_path}"
        else:
            from openwakeword.model import Model
            model = Model(wakeword_model_paths=[resources_model_path])
            model_status, model_msg = "PASS", f"Path resolved & loaded successfully:\n{resources_model_path}"
    except Exception as e:
        model_status, model_msg = "FAIL", f"Model loading failure: {e}"

    if model_status == "FAIL":
        overall_pass = False
        print_error(f"  - {model_msg}")
    else:
        print_success(f"  - {model_msg}")
    print(f"✓ Model Check: {model_status}")
    print("-" * 50)

    # 4. Inference Check
    print_info("Running dummy audio inference on OpenWakeWord...")
    try:
        import openwakeword
        from openwakeword.model import Model
        package_dir = os.path.dirname(openwakeword.__file__)
        model_path = os.path.join(package_dir, "resources", "models", "hey_nova_v0.1.onnx")
        model = Model(wakeword_model_paths=[model_path])
        model_name = os.path.splitext(os.path.basename(model_path))[0]
        dummy_pcm = np.zeros(1280, dtype=np.int16)
        predictions = model.predict(dummy_pcm)
        if model_name not in predictions:
            inf_status, inf_msg = "FAIL", f"Model name key '{model_name}' not found in predictions dictionary: {predictions}"
        else:
            score = predictions.get(model_name, 0.0)
            inf_status, inf_msg = "PASS", f"Inference completed. Score: {score} | Predictions: {predictions}"
    except Exception as e:
        inf_status, inf_msg = "FAIL", f"Inference check error: {e}"

    if inf_status == "FAIL":
        overall_pass = False
        print_error(f"  - {inf_msg}")
    else:
        print_success(f"  - {inf_msg}")
    print(f"✓ Inference Check: {inf_status}")
    print("-" * 50)

    # 5. Signal Check
    print_info("Testing live audio signal capture...")
    try:
        duration = 2.0
        print_info(f"🎤 Recording a {duration}-second audio clip to verify live microphone signal. Please speak...")
        recording = sd.rec(int(duration * 16000), samplerate=16000, channels=1, dtype='float32')
        sd.wait()
        rms = float(np.sqrt(np.mean(np.square(recording))))
        details = f"Frame size: {len(recording)} | RMS Amplitude: {rms:.6f}"
        if rms == 0.0:
            sig_status, sig_msg = "FAIL", f"Captured audio is completely silent. Check mic. Details: {details}"
        else:
            sig_status, sig_msg = "PASS", f"Audio signal verified successfully. Details: {details}"
    except Exception as e:
        sig_status, sig_msg = "FAIL", f"Signal check failure: {e}"

    if sig_status == "FAIL":
        overall_pass = False
        print_error(f"  - {sig_msg}")
    else:
        print_success(f"  - {sig_msg}")
    print(f"✓ Wake-Word Signal Check: {sig_status}")
    print("-" * 50)

    # 6. STT Connection Check
    print_info("Verifying STT pipeline...")
    try:
        stt_provider = get_stt_provider()
        dummy_pcm = np.zeros(16000, dtype=np.int16)
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(dummy_pcm.tobytes())
        wav_bytes = wav_io.getvalue()
        provider_name = "Local Whisper" if "WhisperSTTProvider" in str(type(stt_provider)) else "Remote STT"
        print_info(f"📤 Sending silent query to {provider_name} to verify pipeline...")
        transcription = stt_provider.transcribe(wav_bytes, silent=True)
        stt_status, stt_msg = "PASS", f"({provider_name}) Transcription returned: '{transcription}'"
    except Exception as e:
        stt_status, stt_msg = "FAIL", f"STT pipeline check failure: {e}"

    if stt_status == "FAIL":
        overall_pass = False
        print_error(f"  - {stt_msg}")
    else:
        print_success(f"  - {stt_msg}")
    print(f"✓ STT Check: {stt_status}")
    print("-" * 50)

    # 7. RNNoise Check
    print_info("Verifying RNNoise denoiser...")
    try:
        rn = RNNoiseWrapper()
        if not rn.is_available():
            rn_status, rn_msg = "WARNING", "RNNoise library not found — denoising will be skipped."
        else:
            frame = np.random.randn(160).astype(np.float32) * 0.01
            out = rn.denoise_frame(frame)
            rn.destroy()
            if out.dtype == np.float32:
                rn_status, rn_msg = "PASS", "RNNoise available and working."
            else:
                rn_status, rn_msg = "FAIL", f"RNNoise returned invalid dtype: {out.dtype}"
    except Exception as e:
        rn_status, rn_msg = "FAIL", f"RNNoise check error: {e}"

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
    try:
        agc = AutomaticGainControl()
        quiet = np.ones(480, dtype=np.float32) * 0.01
        agc.process(quiet)
        loud = np.ones(480, dtype=np.float32) * 0.9
        out = agc.process(loud)
        peak = float(np.max(np.abs(out)))
        clipping = int(np.sum(np.abs(out) > 1.0))
        if clipping > 0:
            agc_status, agc_msg = "FAIL", f"AGC produced {clipping} clipped samples (peak={peak:.4f})"
        else:
            agc_status, agc_msg = "PASS", f"AGC anti-clipping OK | peak={peak:.4f} (no clipping)"
    except Exception as e:
        agc_status, agc_msg = "FAIL", f"AGC check error: {e}"

    if agc_status == "FAIL":
        overall_pass = False
        print_error(f"  - {agc_msg}")
    else:
        print_success(f"  - {agc_msg}")
    print(f"✓ AGC Check: {agc_status}")
    print("-" * 50)

    # 9. Audio Diagnostics Check
    print_info("Verifying AudioDiagnostics metrics...")
    try:
        diag = AudioDiagnostics()
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        sig = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        m = diag.measure(sig)
        required = ["rms", "peak", "noise_floor", "clipping_pct", "snr_db", "speech_dur_s"]
        missing  = [k for k in required if k not in m]
        if missing:
            diag_status, diag_msg = "FAIL", f"AudioDiagnostics missing keys: {missing}"
        else:
            diag_status, diag_msg = "PASS", f"rms={m['rms']:.4f} peak={m['peak']:.4f} snr={m['snr_db']:.1f}dB"
    except Exception as e:
        diag_status, diag_msg = "FAIL", f"AudioDiagnostics check error: {e}"

    if diag_status == "FAIL":
        overall_pass = False
        print_error(f"  - {diag_msg}")
    else:
        print_success(f"  - {diag_msg}")
    print(f"✓ AudioDiagnostics Check: {diag_status}")
    print("-" * 50)

    # 10. Speaker Verification Status
    print_info("Checking speaker verification enrollment...")
    try:
        verifier = SpeakerVerifier(
            embedding_path=speaker_embedding_path,
            threshold=speaker_similarity_threshold,
        )
        if not verifier.available:
            sv_status, sv_msg = "WARNING", "resemblyzer not installed — speaker verification disabled."
        elif not verifier.has_profile():
            sv_status, sv_msg = "WARNING", f"No speaker profile enrolled at '{speaker_embedding_path}'."
        else:
            sv_status, sv_msg = "PASS", f"Enrolled embeddings: {verifier.total_embeddings} | Threshold: {speaker_similarity_threshold}"
    except Exception as e:
        sv_status, sv_msg = "FAIL", f"Speaker verification check error: {e}"

    if sv_status == "FAIL":
        overall_pass = False
        print_error(f"  - {sv_msg}")
    elif sv_status == "WARNING":
        print_warning(f"  - {sv_msg}")
    else:
        print_success(f"  - {sv_msg}")
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
        sys.exit(0)
    else:
        print_error("OVERALL STATUS: FAIL")
        sys.exit(1)
