from __future__ import annotations

from nova.voice.pipeline.processors import (
    RNNoiseWrapper,
    HighPassFilter,
    AutomaticGainControl,
    WebRTCVoiceActivityDetector,
    AmbientCalibrator,
    AudioDiagnostics,
    SpeexEchoCanceller,
    NLMSEchoCanceller,
    AecProcessor,
    AudioQualityAnalyzer,
    ConfidenceFusionEngine,
    VoiceDiagnosticsEngine,
    resample_16k_to_48k,
    resample_48k_to_16k,
    select_best_microphone,
    get_reference_chunk,
)

from nova.voice.pipeline.core import (
    VoiceState,
    CircularAudioBuffer,
    VoiceLoopState,
    infer_topic,
    update_working_memory_after_turn,
    get_activation_greeting,
    record_audio,
    calculate_rms,
    run_voice_loop,
    run_voice_self_test,
)

from nova.voice.async_log import async_log, _async_logger
