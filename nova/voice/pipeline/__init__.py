from __future__ import annotations

import sys
import types
import sounddevice as sd

from nova.voice.whisper import get_stt_provider
from nova.voice.wakeword import LocalWakeWordDetector
from nova.voice.speaker import SpeakerVerifier
from nova.voice.tts import speak

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
    process_single_iteration,
)

from nova.voice.pipeline.state_machine import (
    transition_state,
    get_current_state,
    _current_state,
    shutdown_event,
    voice_active_event,
)

from nova.voice.pipeline.interrupts import play_confirmation_sound
from nova.voice.pipeline.wake import _wait_for_wake
from nova.voice.pipeline.recorder import record_audio_from_stream

from nova.voice.async_log import async_log, _async_logger


class PipelineModule(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        try:
            if name == "shutdown_event":
                import nova.voice.pipeline.state_machine as sm
                sm.shutdown_event = value
                import nova.voice.pipeline.core as core
                core.shutdown_event = value
                import nova.voice.pipeline.recorder as recorder
                recorder.shutdown_event = value
                import nova.voice.pipeline.wake as wake
                wake.shutdown_event = value
            elif name == "voice_active_event":
                import nova.voice.pipeline.state_machine as sm
                sm.voice_active_event = value
                import nova.voice.pipeline.core as core
                core.voice_active_event = value
            elif name == "sd":
                import nova.voice.pipeline.core as core
                core.sd = value
            elif name == "get_stt_provider":
                import nova.voice.pipeline.core as core
                core.get_stt_provider = value
            elif name == "LocalWakeWordDetector":
                import nova.voice.pipeline.core as core
                core.LocalWakeWordDetector = value
            elif name == "SpeakerVerifier":
                import nova.voice.pipeline.core as core
                core.SpeakerVerifier = value
            elif name == "speak":
                import nova.voice.pipeline.core as core
                core.speak = value
            elif name == "play_confirmation_sound":
                import nova.voice.pipeline.core as core
                core.play_confirmation_sound = value
            elif name == "_wait_for_wake":
                import nova.voice.pipeline.core as core
                core._wait_for_wake = value
            elif name == "record_audio_from_stream":
                import nova.voice.pipeline.core as core
                core.record_audio_from_stream = value
            elif name == "AudioQualityAnalyzer":
                import nova.voice.pipeline.core as core
                core.AudioQualityAnalyzer = value
            elif name == "AmbientCalibrator":
                import nova.voice.pipeline.core as core
                core.AmbientCalibrator = value
            elif name == "HighPassFilter":
                import nova.voice.pipeline.core as core
                core.HighPassFilter = value
            elif name == "RNNoiseWrapper":
                import nova.voice.pipeline.core as core
                core.RNNoiseWrapper = value
            elif name == "AecProcessor":
                import nova.voice.pipeline.core as core
                core.AecProcessor = value
            elif name == "WebRTCVoiceActivityDetector":
                import nova.voice.pipeline.core as core
                core.WebRTCVoiceActivityDetector = value
        except Exception:
            pass


sys.modules[__name__].__class__ = PipelineModule
