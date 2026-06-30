# Nova Voice Interface Setup Guide

This document describes how to configure and install the required Python packages and native system libraries to enable Voice Mode support in Nova.

## Python Packages Installation

Activate your virtual environment and install the required voice-related dependencies:

```bash
source .venv/bin/activate
python -m pip install -r requirements-voice.txt
```

## Native NixOS Dependencies

Because Nova runs on NixOS, native system packages required for audio recording, media handling, and waveform manipulation must be supplied by the Nix environment. The required native dependencies are:

- `portaudio` (for audio input/output via `sounddevice`)
- `libsndfile` (for reading and writing audio files via `soundfile`)
- `ffmpeg` (for media processing / format conversion)

### Setup via `shell.nix`

If you are using a development shell (`shell.nix`), you can add these native libraries to your environment. Here is a sample `shell.nix` that configures both Python and the necessary system library paths:

```nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    portaudio
    libsndfile
    ffmpeg
    mpg123 # Optional, used for playing text-to-speech audio
  ];

  shellHook = ''
    # Ensure system shared libraries can be loaded by Python packages (like sounddevice and soundfile)
    export LD_LIBRARY_PATH="${pkgs.portaudio}/lib:${pkgs.libsndfile}/lib:${pkgs.ffmpeg}/lib:$LD_LIBRARY_PATH"
    
    # Auto-activate your virtual environment if it exists
    if [ -d .venv ]; then
      source .venv/bin/activate
    fi
  '';
}
```

To enter this environment, simply run:

```bash
nix-shell
```

### Setup via `flake.nix`

If you are using Nix Flakes, you can define a development environment like this:

```nix
{
  description = "Nova Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = with pkgs; [
          python3
          portaudio
          libsndfile
          ffmpeg
          mpg123
        ];

        shellHook = ''
          export LD_LIBRARY_PATH="${pkgs.portaudio}/lib:${pkgs.libsndfile}/lib:${pkgs.ffmpeg}/lib:$LD_LIBRARY_PATH"
          if [ -d .venv ]; then
            source .venv/bin/activate
          fi
        '';
      };
    };
}
```

To enter the flake environment, run:

```bash
nix develop
```

## Audio Preprocessing Pipeline Upgrades

Nova's voice preprocessing pipeline (`audio_processor.py`) has been upgraded with robust DSP enhancements designed to maximize speech recognition accuracy and eliminate common audio issues:

1. **Click-Resistant Ambient Calibration:**
   * **Mechanism:** Rather than taking the average RMS of startup ambient noise (which is vulnerable to mouse clicks, breaths, or typing taps), the `AmbientCalibrator` computes the RMS of 30ms frames and selects the **10th percentile** frame energy as the noise floor.
   * **Benefit:** Ensures that single loud transient spikes do not inflate the calibrated noise floor, preventing VAD failure.

2. **AGC Noise-Pumping Prevention:**
   * **Mechanism:** The `AutomaticGainControl` features a noise gate threshold (`noise_floor * 1.5`). Adaptation is frozen when speech is inactive or the input RMS falls below this threshold.
   * **Benefit:** Prevents the AGC from boosting background mic hiss/static to high volume during pauses/silence.

3. **Steeper Nyquist-Safeguarded High-Pass Filter:**
   * **Mechanism:** `HighPassFilter` validates that the cutoff frequency lies safely below the Nyquist limit (`0 < cutoff < 0.5 * fs`).
   * **Benefit:** Gracefully bypasses filtering without crashing if running under non-standard sampling rates or misconfigured cutoffs.

4. **WebRTC VAD Hangover & Multi-Sizing:**
   * **Mechanism:** WebRTC VAD requires exact 10ms, 20ms, or 30ms frames. If a non-standard frame size is passed, `WebRTCVoiceActivityDetector` dynamically chunks the array into 10ms subframes, zero-pads the remaining tail, and runs VAD on each block. A hangover counter (8 frames) keeps the state as `True` during brief syllable pauses.
   * **Benefit:** Prevents VAD crashes under dynamic audio buffers and eliminates VAD flickering between syllables.

5. **Arbitrary Chunk RNNoise Denoising:**
   * **Mechanism:** `RNNoiseWrapper.denoise_chunk()` zero-pads arbitrary length inputs to the nearest multiple of 480 samples, processes them in bulk, and crops them back to the original length.
   * **Benefit:** Enables zero-latency noise suppression on any arbitrary audio buffer layout.

6. **Speaker Verification Multi-Embedding System:**
   * **Mechanism:** Replaces the single average speaker embedding with a profile version `2.0` multi-embedding layout. New speaker embeddings are evaluated for quality and verified as non-duplicates before addition. If capacity is exceeded, low-quality embeddings are cleaned up automatically. Matrix-vector dot products are used for fast nearest-neighbour score comparison.
   * **Benefit:** Increases robustness across different speaking volumes, background noise, and microphone setups, with automatic profile maintenance.

7. **Confidence Fusion Engine:**
   * **Mechanism:** A modular decision layer (`confidence_fusion.py`) that fuses wake-word confidence, speaker verification confidence, WebRTC VAD probability, audio quality estimation, and noise floor into a single fused score.
   * **Benefit:** Supports custom configurable weights, dynamically normalises weights if sources are missing or disabled, integrates with diagnostics logging, and supports registering future custom score providers.

8. **Continuous Speaker Learning:**
   * **Mechanism:** 
     * **Interaction Staging:** Verify matches stage the speaker embedding as a pending candidate. It is committed ONLY after successful command action execution.
     * **Anchor-Based Drift Prevention:** Verifies that candidate embeddings have a cosine similarity of at least `0.70` to at least one of the initial enrollment anchor embeddings.
     * **Backup and Rollback:** Saves backups (`speaker_profile.json.bak` and `speaker_embeddings.npy.bak`) before saving adaptations, allowing `rollback()` to restore the profile state.
     * **Config Toggle:** Can be fully disabled by setting `ENABLE_SPEAKER_CONTINUOUS_LEARNING = False` in `config.py`.
   * **Benefit:** Adapts dynamically to changing speaker conditions (cold/hoarse voice, new microphones) without losing voice footprint bounds.

9. **Adaptive Wake Behaviour:**
   * **Mechanism:**
     * **Dynamic Scaling:** An environment-aware threshold manager (`adaptive_wake.py`) dynamically scales wake word confidence, VAD noise thresholds, silence timeouts, and speaker verification similarity thresholds.
     * **Input Metrics:** Scaling is calculated in real-time from background noise floor, speech SNR, microphone clipping metrics, and recent trigger success rates.
     * **User Override Checks:** Verifies `os.environ` keys dynamically and skips adjusting variables if custom overrides are defined.
     * **Adaptation Logs:** Appends every threshold modification event to `~/.config/nova/adaptive_wake_logs.json`.
   * **Benefit:** Maximizes wake sensitivity in quiet settings while automatically reducing false activations and flicker rejections in noisy or harsh conditions.

10. **Acoustic Echo Cancellation (AEC):**
    * **Mechanism:**
      * **Reference Synchronization:** When TTS playback begins, the audio file is eagerly decoded/resampled to 16 kHz mono and cached as a reference signal. Real-time time-sync alignment tracks the playback cursor offset relative to the microphone stream.
      * **Dual AEC Engines:** Try loading native SpeexDSP (`libspeexdsp.so`) via ctypes for extremely low-latency, hardware-optimized cancellation. Fall back to a vectorized Normalized Least Mean Squares (NLMS) adaptive filter in pure NumPy if the library is not found.
      * **Denoising Integration:** Processes microphone input chunks prior to wake-word detection (`check_for_wake_interrupt`), idle listening (`_wait_for_wake`), and voice recording (`record_audio_from_stream`).
      * **Configuration:** Can be enabled/disabled using `ENABLE_ECHO_CANCEL` in `config.py` (or via environment variables).
    * **Benefit:** Prevents Nova from hearing its own output speech, avoiding self-interruption and false wake triggers during active speech playback, while maintaining optimal streaming performance.

11. **Audio Quality Analysis:**
    * **Mechanism:**
      * **Multi-dimensional Metrics:** An analyzer (`audio_quality.py`) evaluates SNR (dB), background noise floor (RMS), microphone clipping percentage, active voice volume (RMS), and echo level (normalized cross-correlation against the playing reference signal).
      * **Combined Quality Score:** Integrates these parameters into a single normalized score in `[0.0, 1.0]`.
      * **API Exposition:** Exposes `AudioQualityAnalyzer.analyze(audio, ref_audio=None) -> dict`.
      * **Confidence Fusion Integration:** Integrates with the `ConfidenceFusionEngine` in the wake-word trigger path, using the calculated `overall_quality` score and `background_noise` floor as inputs for the unified trigger decision.
      * **Diagnostics Integration:** Appends the full metrics dict under `scores` and `weights` in `~/.config/nova/fusion_logs.json`.
    * **Benefit:** Ensures that trigger decisions are robust under high-noise, clipping, or echo conditions, and provides deep insights into the recording environment.







