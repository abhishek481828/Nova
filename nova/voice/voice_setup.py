"""
Nova Voice Setup — Speaker Enrollment Wizard.

Usage:
    python -m nova.voice.voice_setup
    nova voice-setup
"""

from __future__ import annotations

import sys
import os
import glob

# ---------------------------------------------------------------------------
# Path bootstrap (mirrors voice_test.py pattern)
# ---------------------------------------------------------------------------
try:
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    for _venv_dir in glob.glob(os.path.join(_project_root, ".venv", "lib", "python*", "site-packages")):
        if _venv_dir not in sys.path:
            sys.path.append(_venv_dir)
except Exception:
    pass

# ---------------------------------------------------------------------------
import time
import numpy as np
import sounddevice as sd

from nova.voice.config import (
    SAMPLE_RATE, CHANNELS,
    enable_speaker_verification,
    speaker_similarity_threshold,
    speaker_embedding_path,
)
from nova.voice.speaker_verify import SpeakerVerifier, _RESEMBLYZER_AVAILABLE
from nova.utils import (
    print_info, print_warning, print_error, print_success,
    COLOR_BOLD, COLOR_RESET,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENROLL_PHRASE    = "Hey Nova, this is my voice."
NUM_SAMPLES      = 7          # recommended number of recordings
MIN_SAMPLES      = 3          # minimum accepted
RECORD_DURATION  = 3.0        # seconds per sample
SILENCE_PADDING  = 0.3        # seconds to skip at start for mic stabilisation


def _record_sample(index: int, total: int) -> np.ndarray | None:
    """
    Prompt the user and record one audio sample.
    Returns float32 numpy array (shape: [n_samples]), or None on abort/error.
    """
    try:
        prompt = input(
            f"  Sample {index}/{total} — Press ENTER to record (or 'q' to quit)... "
        ).strip().lower()
    except (KeyboardInterrupt, EOFError):
        return None

    if prompt == "q":
        return None

    # Short padding so mic AGC can stabilise before user speaks
    time.sleep(SILENCE_PADDING)
    print_info(f'  🎤 Recording ({RECORD_DURATION}s) — say: "{ENROLL_PHRASE}"')

    try:
        audio = sd.rec(
            int(RECORD_DURATION * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
        )
        sd.wait()
        return audio.flatten()
    except Exception as e:
        print_error(f"  Recording failed: {e}")
        return None


def main() -> None:
    print(f"\n{COLOR_BOLD}=== NOVA VOICE SETUP ==={COLOR_RESET}\n")

    # Guard: Resemblyzer must be available
    if not _RESEMBLYZER_AVAILABLE:
        print_error("resemblyzer is not installed.")
        print_info("Run:  pip install resemblyzer")
        sys.exit(1)

    verifier = SpeakerVerifier(
        embedding_path=speaker_embedding_path,
        threshold=speaker_similarity_threshold,
    )

    # Warn if re-enrolling
    if verifier.has_profile():
        meta = verifier.meta()
        if meta:
            print_warning(
                f"An existing profile was enrolled on {meta.get('enrolled_at', '?')} "
                f"({meta.get('samples', '?')} samples)."
            )
        try:
            overwrite = input("Re-enroll and overwrite? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(0)
        if overwrite not in ("y", "yes"):
            print_info("Enrollment cancelled.")
            sys.exit(0)

    print_info(f'You will be asked to say the following phrase {NUM_SAMPLES} times:')
    print(f'\n    {COLOR_BOLD}"{ENROLL_PHRASE}"{COLOR_RESET}\n')
    print_info(f"Speak clearly and at a normal pace. Minimum {MIN_SAMPLES} samples required.")
    print()

    samples: list[np.ndarray] = []
    for i in range(1, NUM_SAMPLES + 1):
        audio = _record_sample(i, NUM_SAMPLES)
        if audio is None:
            print_warning(f"Sample {i} skipped or aborted.")
            if len(samples) >= MIN_SAMPLES:
                try:
                    finish = input(
                        f"  {len(samples)} samples collected. Enroll with these? [y/N] "
                    ).strip().lower()
                    if finish in ("y", "yes"):
                        break
                except (KeyboardInterrupt, EOFError):
                    pass
            if i == NUM_SAMPLES:
                break
            continue

        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.005:
            print_warning("  ⚠ Very low audio level — check microphone and try again.")
        else:
            print_success(f"  ✔ Sample {i} recorded (RMS: {rms:.4f})")
            samples.append(audio)

    if len(samples) < MIN_SAMPLES:
        print_error(
            f"Not enough valid samples ({len(samples)} < {MIN_SAMPLES}). "
            "Enrollment aborted."
        )
        sys.exit(1)

    print()
    print_info(f"Extracting speaker embeddings from {len(samples)} samples...")

    try:
        verifier.enroll(samples, sr=SAMPLE_RATE)
    except Exception as e:
        print_error(f"Enrollment failed: {e}")
        sys.exit(1)

    print_success(f"Speaker profile saved to:")
    print_success(f"  {speaker_embedding_path}")
    print()
    print_info("You can test your profile with:  nova voice-test")
    print_info("You can delete your profile with: nova voice-reset")


if __name__ == "__main__":
    main()
