"""
Nova Voice Reset — Delete enrolled speaker profile.

Usage:
    python -m nova.voice.voice_reset
    nova voice-reset
"""

from __future__ import annotations

import sys
import os
import glob

# ---------------------------------------------------------------------------
# Path bootstrap
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
from nova.voice.config import speaker_embedding_path, speaker_similarity_threshold
from nova.voice.speaker_verify import SpeakerVerifier
from nova.utils import print_info, print_warning, print_error, print_success, COLOR_BOLD, COLOR_RESET


def main() -> None:
    print(f"\n{COLOR_BOLD}=== NOVA VOICE RESET ==={COLOR_RESET}\n")

    verifier = SpeakerVerifier(
        embedding_path=speaker_embedding_path,
        threshold=speaker_similarity_threshold,
    )

    if not verifier.has_profile():
        print_info("No enrolled speaker profile found. Nothing to delete.")
        sys.exit(0)

    meta = verifier.meta()
    if meta:
        print_warning(
            f"Profile enrolled on {meta.get('enrolled_at', '?')} "
            f"({meta.get('samples', '?')} samples)."
        )

    print_warning("This will permanently delete your speaker profile.")
    try:
        confirm = input("Type 'yes' to confirm deletion: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        print_info("Reset cancelled.")
        sys.exit(0)

    if confirm != "yes":
        print_info("Reset cancelled.")
        sys.exit(0)

    deleted = verifier.delete_profile()
    if deleted:
        print_success("Speaker profile deleted.")
        print_info('Voice Mode will use wake-word detection only until you run "nova voice-setup".')
    else:
        print_error("Failed to delete profile — files may have already been removed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
