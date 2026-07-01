#!/usr/bin/env python3
import sys
import os
import glob

# Include project root and venv site-packages
try:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
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
except Exception as e:
    print(f"Path bootstrap error: {e}")

import time
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False

try:
    import sounddevice as sd
    from nova.voice.config import speaker_embedding_path, speaker_similarity_threshold, SAMPLE_RATE, CHANNELS
    from nova.voice.speaker import SpeakerVerifier, _RESEMBLYZER_AVAILABLE
    from nova.utils import print_info, print_success, print_warning, print_error, COLOR_BOLD, COLOR_RESET
    _VOICE_AVAILABLE = True
except ImportError:
    sd = SpeakerVerifier = None  # type: ignore
    _VOICE_AVAILABLE = False

def main():
    print(f"\n{COLOR_BOLD}=== NOVA VOICE PROFILE TESTER ==={COLOR_RESET}\n")

    if not _RESEMBLYZER_AVAILABLE:
        print_error("resemblyzer is not installed or available.")
        print_info("To install, run: source .venv/bin/activate && pip install resemblyzer")
        sys.exit(1)

    verifier = SpeakerVerifier(
        embedding_path=speaker_embedding_path,
        threshold=speaker_similarity_threshold,
    )

    if not verifier.has_profile():
        print_error("No enrolled voice profile found!")
        print_info(f"Expected profile at: {speaker_embedding_path}")
        print_info("Please enroll first by running: nova voice-setup")
        sys.exit(1)

    meta = verifier.meta()
    print_info(f"Loaded enrolled profile from: {speaker_embedding_path}")
    print(f"  Enrolled at : {meta.get('enrolled_at', 'Unknown')}")
    print(f"  Samples     : {len(meta.get('embeddings', []))}")
    print(f"  Threshold   : {verifier._threshold:.4f}")
    print("-" * 50)

    duration = 4.0
    print_info(f"Prepare to speak for {duration} seconds.")
    print_info("Press ENTER and say a wake phrase like: 'Hey Nova, this is my voice.'")
    try:
        input("\n[Press Enter to start recording]")
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(0)

    time.sleep(0.2)
    print(f"\n🎤 {COLOR_BOLD}RECORDING... (Please speak now){COLOR_RESET}")

    try:
        recording = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
        )
        sd.wait()
        print_success("Recording complete!")
    except Exception as e:
        print_error(f"Failed to record audio: {e}")
        sys.exit(1)

    audio = recording.flatten()
    rms = float(np.sqrt(np.mean(audio ** 2)))
    print(f"\nCaptured audio RMS level: {rms:.6f}")
    if rms < 0.002:
        print_warning("⚠ The recorded audio level is very low. Please speak louder/closer to the microphone.")

    print_info("Running speaker verification analysis...")
    is_match, similarity_score = verifier.verify(audio, SAMPLE_RATE)

    print("\n" + "=" * 50)
    print(f"{COLOR_BOLD}RESULTS:{COLOR_RESET}")
    print(f"  Similarity Score : {similarity_score if similarity_score is not None else 0.0:.4f}")
    print(f"  Match Threshold  : {verifier._threshold:.4f}")
    
    if is_match and similarity_score is not None:
        print_success(f"✔ MATCH SUCCESSFUL (Score: {similarity_score:.4f} >= Threshold: {verifier._threshold:.4f})")
        print_success("Your voice matches the enrolled profile.")
    else:
        score_str = f"{similarity_score:.4f}" if similarity_score is not None else "N/A"
        print_error(f"✘ MATCH FAILED (Score: {score_str} < Threshold: {verifier._threshold:.4f})")
        print_error("Your voice does NOT match the enrolled profile.")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    main()
