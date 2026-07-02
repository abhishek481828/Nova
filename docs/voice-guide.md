# Voice Guide

This document describes the design of Nova's real-time voice pipeline.

---

## Processing Flow
1.  **Microphone Capture**: sounddevice polls InputStream at `16000Hz` sample rate.
2.  **DSP Filters**:
    *   **High Pass Filter**: Cuts sub-80Hz low-frequency rumble.
    *   **Automatic Gain Control (AGC)**: Regulates input volume.
3.  **VAD**: WebRTC Voice Activity Detection suppresses silence frame processing.
4.  **Wake Detection**: OpenWakeWord checks frames against the `hey_nova_v0.1` ONNX model.
5.  **Speaker Verification**: Resemblyzer confirms identity.
