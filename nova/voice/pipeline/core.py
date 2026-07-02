"""
Consolidated audio pipeline and state machine orchestration for the Nova Voice subsystem.
"""
from __future__ import annotations

import os
import re
import time
import json
import queue
import threading
import collections
import random
import subprocess
import wave
import io
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np

import nova.voice.config as voice_config
from nova.voice.config import (
    SAMPLE_RATE, CHANNELS, RECORDING_TIMEOUT, SILENCE_TIMEOUT, TEMP_AUDIO_DIR,
    VAD_THRESHOLD, NOISE_FLOOR_MARGIN, HIGHPASS_CUTOFF, VAD_AGGRESSIVENESS,
    ENABLE_NOISE_SUPPRESSION, ENABLE_HIGHPASS_FILTER, ENABLE_AGC, ENABLE_VAD,
    ENABLE_DC_OFFSET_REMOVAL, BLOCK_SIZE,
    VAD_PRE_PADDING_FRAMES, VAD_POST_PADDING_FRAMES, enable_debug,
    enable_wake_word, wake_word_phrase, wake_word_model_path,
    wake_word_threshold, confirmation_sound, enable_speaker_verification,
    speaker_similarity_threshold, speaker_embedding_path,
    AGC_TARGET_RMS, AGC_MAX_GAIN, AGC_RATE, AMBIENT_CALIBRATION_DURATION,
)
from nova.logger import logger
import sounddevice as sd
from nova.utils import (
    print_info, print_warning, print_error, print_success,
    COLOR_BOLD, COLOR_RESET, COLOR_CYAN, COLOR_RED
)

from nova.voice.speaker import SpeakerVerifier
from nova.voice.whisper import get_stt_provider
from nova.voice.tts import speak
from nova.voice.wakeword import LocalWakeWordDetector, AdaptiveWakeController


from nova.voice.async_log import async_log
from nova.voice.pipeline.processors import (
    RNNoiseWrapper,
    HighPassFilter,
    AutomaticGainControl,
    WebRTCVoiceActivityDetector,
    AmbientCalibrator,
    AudioDiagnostics,
    AecProcessor,
    AudioQualityAnalyzer,
    ConfidenceFusionEngine,
    VoiceDiagnosticsEngine,
    resample_16k_to_48k,
    resample_48k_to_16k,
    select_best_microphone,
    get_reference_chunk,
)

# ---------------------------------------------------------------------------
# Re-exports and imports from sub-modules for backwards compatibility
# ---------------------------------------------------------------------------
import nova.voice.pipeline.state_machine as sm
from nova.voice.pipeline.greetings import (
    _recent_greetings, _get_user_name, get_activation_greeting
)
from nova.voice.pipeline.recorder import (
    calculate_rms, CircularAudioBuffer, record_audio, record_audio_from_stream
)
from nova.voice.pipeline.state_machine import (
    VoiceState, voice_active_event, shutdown_event, transition_state,
    get_current_state, get_voice_status_report, set_deferred_deactivate,
    recover_microphone, recover_wake_detector, check_long_running_action
)
from nova.voice.pipeline.interrupts import (
    clean_ansi, _is_interrupt_phrase, _start_background_interrupt_listener,
    _stop_background_interrupt_listener, play_confirmation_sound,
    get_user_confirmation
)
from nova.voice.pipeline.memory import infer_topic, update_working_memory_after_turn
from nova.voice.pipeline.wake import _wait_for_wake
from nova.voice.pipeline.diagnostics import run_voice_self_test





class VoiceLoopState:
    def __init__(self, diagnostics=None, working_memory=None):
        self.stt_provider = None
        self.verifier = None
        self.stream = None
        self.wake_detector = None
        self.adaptive_wake_ctrl = AdaptiveWakeController()
        self.fusion_engine = ConfidenceFusionEngine()
        self.quality_analyzer = AudioQualityAnalyzer()
        self.diagnostics = diagnostics if diagnostics is not None else VoiceDiagnosticsEngine()
        import nova.voice.config as _vc_cfg
        _vc_cfg.active_diagnostics = self.diagnostics

        from nova.core.memory import WorkingMemory
        self.working_memory = working_memory if working_memory is not None else WorkingMemory()
        self.use_wake_word = enable_wake_word
        self.noise_floor = VAD_THRESHOLD
        self.speech_threshold = VAD_THRESHOLD + NOISE_FLOOR_MARGIN
        self.calibrated = False
        self._greeted_this_activation = False
        self._first_ptt_since_activation = False
        self.last_command_snr = None
        self.last_clipping_pct = None
        self.skip_idle_wait = False
        self.hp_filter = None
        self.rnnoise = None
        self.agc = None
        self.vad = None
        self.aec = None
        self.current_state = VoiceState.INACTIVE
        self.last_printed_state = None





def process_single_iteration(
    state: VoiceLoopState,
    ai_client,
    dispatcher,
    transition_to
) -> str:

    stt_provider = state.stt_provider
    verifier = state.verifier
    stream = state.stream
    wake_detector = state.wake_detector
    adaptive_wake_ctrl = state.adaptive_wake_ctrl
    fusion_engine = state.fusion_engine
    quality_analyzer = state.quality_analyzer
    diagnostics = state.diagnostics
    use_wake_word = state.use_wake_word
    noise_floor = state.noise_floor
    speech_threshold = state.speech_threshold
    calibrated = state.calibrated
    _greeted_this_activation = state._greeted_this_activation
    _first_ptt_since_activation = state._first_ptt_since_activation
    last_command_snr = state.last_command_snr
    last_clipping_pct = state.last_clipping_pct
    skip_idle_wait = state.skip_idle_wait
    hp_filter = state.hp_filter
    rnnoise = state.rnnoise
    agc = state.agc
    vad = state.vad
    aec = state.aec
    last_printed_state = state.last_printed_state

    def save_state():
        state.stt_provider = stt_provider
        state.verifier = verifier
        state.stream = stream
        state.wake_detector = wake_detector
        state.noise_floor = noise_floor
        state.speech_threshold = speech_threshold
        state.calibrated = calibrated
        state._greeted_this_activation = _greeted_this_activation
        state._first_ptt_since_activation = _first_ptt_since_activation
        state.last_command_snr = last_command_snr
        state.last_clipping_pct = last_clipping_pct
        state.skip_idle_wait = skip_idle_wait
        state.hp_filter = hp_filter
        state.rnnoise = rnnoise
        state.agc = agc
        state.vad = vad
        state.aec = aec
        state.last_printed_state = last_printed_state

    quality_metrics = None
    speaker_score = None
    cmd_start = time.time()
    assistant_reply = ""

    if sm._current_state in (VoiceState.INACTIVE, VoiceState.TEXT_MODE):
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            stream = None
            voice_config.active_stream = None
            sm._mic_healthy = False
        _greeted_this_activation = False
        _first_ptt_since_activation = True
        
        while sm._current_state in (VoiceState.INACTIVE, VoiceState.TEXT_MODE) and not shutdown_event.is_set():
            if voice_active_event.is_set():
                voice_active_event.clear()
                transition_to(VoiceState.VOICE_IDLE)
                break
            time.sleep(0.1)
        save_state()
        return "continue"

    try:
        state.working_memory.set("listening_state", "idle")
        state.working_memory.set("wake_word_activation", False)
        state.working_memory.set("recognition_confidence", 0.0)
        state.working_memory.set("current_speaker", None)
        state.working_memory.set("final_transcription", None)
    except Exception as e:
        logger.debug(f"Failed to reset turn memory: {e}")

    if sm._current_state == VoiceState.VOICE_IDLE:
        if stt_provider is None:
            try:
                stt_provider = get_stt_provider()
                sm._stt_healthy = True
            except Exception as e:
                logger.error(f"Failed to initialize STT provider: {e}")
                sm._stt_healthy = False
                stt_provider = None

        if verifier is None and enable_speaker_verification:
            verifier = SpeakerVerifier(
                embedding_path=speaker_embedding_path,
                threshold=speaker_similarity_threshold,
            )
            if not verifier.available:
                print_warning("resemblyzer not installed — speaker verification disabled.")
                verifier = None
            elif not verifier.has_profile():
                print_warning('No enrolled voice profile found. Using wake-word only. Run "nova voice-setup" to enroll.')
                verifier = None

        if stream is None:
            try:
                if not sd.query_devices(kind="input"):
                    raise RuntimeError("No input device found.")
                stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32")
                stream.start()
                sm._mic_healthy = True
                voice_config.active_stream = stream
            except Exception as e:
                print_error(f"Failed to open microphone: {e}")
                sm._mic_healthy = False
                transition_to(VoiceState.INACTIVE)
                save_state()
                return "continue"

        if not calibrated:
            try:
                calib_n = int(SAMPLE_RATE * AMBIENT_CALIBRATION_DURATION)
                with voice_config.stream_lock:
                    calib_audio, _ = stream.read(calib_n)
                calibrator = AmbientCalibrator()
                calibrator.calibrate(calib_audio)
                noise_floor = calibrator.noise_floor
                speech_threshold = calibrator.speech_threshold
                if noise_floor > 0.5:
                    speech_threshold = 0.02
                calibrated = True
            except Exception as e:
                logger.debug(f"Calibration error: {e}")
                print_warning("Calibration failed — using defaults.")
                calibrated = True

        if hp_filter is None:
            try:
                aec = AecProcessor() if voice_config.ENABLE_ECHO_CANCEL else None
                voice_config.active_aec = aec
                hp_filter = HighPassFilter(cutoff=HIGHPASS_CUTOFF, fs=SAMPLE_RATE) if ENABLE_HIGHPASS_FILTER else None
                rnnoise = RNNoiseWrapper() if ENABLE_NOISE_SUPPRESSION else None
                agc = AutomaticGainControl() if ENABLE_AGC else None
                vad = WebRTCVoiceActivityDetector(aggressiveness=VAD_AGGRESSIVENESS, default_threshold=speech_threshold) if ENABLE_VAD else None
            except Exception as e:
                logger.debug(f"Failed to initialize persistent preprocessors: {e}")

        use_wake_word = enable_wake_word
        if wake_detector is None and use_wake_word:
            try:
                wake_detector = LocalWakeWordDetector(
                    model_path=wake_word_model_path,
                    confidence_threshold=wake_word_threshold,
                )
                sm._wake_healthy = True
                voice_config.active_wake_detector = wake_detector
            except Exception as e:
                logger.debug(f"Wake-engine load error: {e}")
                sm._wake_healthy = False
                use_wake_word = False

        if not _greeted_this_activation:
            _greeted_this_activation = True
            try:
                greeting_text = get_activation_greeting()
                speak(greeting_text)
                time.sleep(0.3)
                if stream is not None:
                    with voice_config.stream_lock:
                        if stream.read_available > 0:
                            stream.read(stream.read_available)
            except Exception:
                pass

    if not skip_idle_wait:
        if verifier is not None:
            verifier.clear_pending_adaptation()
        
        try:
            adapted = adaptive_wake_ctrl.adapt(
                noise_floor,
                signal_quality_snr=last_command_snr,
                clipping_pct=last_clipping_pct
            )
            if wake_detector is not None:
                wake_detector.confidence_threshold = adapted["wake_threshold"]
            if verifier is not None:
                verifier._threshold = adapted["speaker_threshold"]
        except Exception as adapt_err:
            logger.debug(f"Threshold adaptation error: {adapt_err}")

        if use_wake_word:
            transition_to(VoiceState.VOICE_IDLE)
            if last_printed_state != VoiceState.VOICE_IDLE:
                print_info(f'👂 Waiting for "{wake_word_phrase}"')
                last_printed_state = VoiceState.VOICE_IDLE
            detected, wake_audio, wake_score = _wait_for_wake(stream, wake_detector, noise_floor)
            if _current_state == VoiceState.INACTIVE:
                save_state()
                return "continue"
            if not detected:
                if shutdown_event.is_set():
                    save_state()
                    return "break"
                save_state()
                return "continue"

            try:
                try:
                    from nova.dashboard.event_bus import emit
                    emit("wake_word_detected", module="voice", status="success", metadata={"detector": "OpenWakeWord"})
                except Exception:
                    pass

                transition_to(VoiceState.WAKE_DETECTED)
                if wake_audio is not None:
                    quality_metrics = quality_analyzer.analyze(wake_audio)
                    vad_frames = 0
                    total_frames = len(wake_audio) // 480
                    if total_frames > 0 and vad is not None:
                        for i in range(total_frames):
                            chunk = wake_audio[i*480 : (i+1)*480]
                            if vad.is_speech(chunk, SAMPLE_RATE):
                                vad_frames += 1
                        vad_score = vad_frames / total_frames
                    else:
                        vad_score = None
                        
                    speaker_score = None
                    if verifier is not None:
                        _, speaker_score = verifier.verify(wake_audio, SAMPLE_RATE)
                        
                    _raw_wake = wake_score
                    _wake_detect_thresh = 0.07
                    if _raw_wake >= _wake_detect_thresh:
                        normalized_wake = 0.70 + 0.30 * min(1.0, (_raw_wake - _wake_detect_thresh) / (1.0 - _wake_detect_thresh))
                    else:
                        normalized_wake = _raw_wake

                    normalized_speaker = speaker_score
                    if speaker_score is not None and verifier is not None:
                        _spk_thresh = verifier._threshold
                        if speaker_score >= _spk_thresh:
                            normalized_speaker = 0.70 + 0.30 * min(1.0, (speaker_score - _spk_thresh) / (1.0 - _spk_thresh))
                        else:
                            normalized_speaker = 0.70 * (speaker_score / _spk_thresh) if _spk_thresh > 0 else speaker_score

                    fused_score = fusion_engine.fuse(
                        wake_score=normalized_wake,
                        speaker_score=normalized_speaker,
                        vad_score=vad_score,
                        audio_quality=quality_metrics["overall_quality"],
                        noise_level=quality_metrics["background_noise"]
                    )
                    
                    if enable_debug:
                        logger.debug(
                            f"[FUSION] raw_wake={wake_score:.3f} norm_wake={normalized_wake:.3f} "
                            f"raw_speaker={str(speaker_score)} norm_speaker={str(normalized_speaker)} "
                            f"vad={str(vad_score)} quality={quality_metrics['overall_quality']:.3f} "
                            f"noise={quality_metrics['background_noise']:.5f} -> fused={fused_score:.3f}"
                        )
                        print_info(f"Fused confidence score: {fused_score:.3f}")
                        
                    fusion_threshold = getattr(voice_config, "FUSION_TRIGGER_THRESHOLD", 0.50)

                    if getattr(voice_config, "ENABLE_VOICE_DEBUG", False):
                        wake_threshold = wake_detector.confidence_threshold if wake_detector is not None else getattr(voice_config, "WAKE_WORD_THRESHOLD", 0.30)
                        speaker_threshold = verifier._threshold if verifier is not None else getattr(voice_config, "speaker_similarity_threshold", 0.75)
                        decision = "ACCEPTED" if fused_score >= fusion_threshold else "REJECTED"
                        
                        reason = "N/A"
                        if decision == "REJECTED":
                            if wake_score < wake_threshold:
                                reason = "Wake-word confidence too low"
                            elif verifier is not None and speaker_score is not None and speaker_score < speaker_threshold:
                                reason = "Speaker similarity too low"
                            else:
                                reason = "Overall fusion score too low"

                        wake_val = f"{wake_score:.4f}"
                        speaker_val = f"{speaker_score:.4f}" if speaker_score is not None else "N/A"
                        vad_val = f"{vad_score:.4f}" if vad_score is not None else "N/A"
                        quality_val = f"{quality_metrics.get('overall_quality'):.4f}" if quality_metrics else "N/A"
                        noise_val = f"{quality_metrics.get('background_noise'):.6f}" if quality_metrics else "N/A"
                        
                        print("\n--- Voice Debug Mode ---")
                        print(f"Wake-word model score           : {wake_val}")
                        print(f"Speaker verification similarity : {speaker_val}")
                        print(f"Speaker threshold               : {speaker_threshold:.4f}")
                        print(f"Fusion inputs                   : wake={wake_val}, speaker={speaker_val}, vad={vad_val}, quality={quality_val}, noise={noise_val}")
                        print(f"Final fusion score              : {fused_score:.4f}")
                        print(f"Fusion threshold                : {fusion_threshold:.4f}")
                        print(f"Ambient noise estimate          : {f'{noise_floor:.6f}' if noise_floor is not None else 'N/A'}")
                        print(f"Decision                        : {decision}")
                        print(f"Exact reason for rejection      : {reason}")
                        print("------------------------\n")
                        
                    if fused_score < fusion_threshold:
                        print_warning(
                            f"Trigger rejected by Confidence Fusion Engine (score {fused_score:.2f} < {fusion_threshold}) — continuing to listen."
                        )
                        diagnostics.record_audio_quality(quality_metrics)
                        save_state()
                        return "continue"

                    speech_start_t = getattr(wake_detector, "last_speech_start_time_abs", None)
                    if speech_start_t is not None:
                        wake_latency_ms = (time.time() - speech_start_t) * 1000.0
                    else:
                        wake_latency_ms = 800.0
                        if hasattr(wake_detector, "diagnostics_history") and wake_detector.diagnostics_history:
                            last_diag = wake_detector.diagnostics_history[-1]
                            if last_diag.get("event") == "wake_trigger":
                                wake_latency_ms = last_diag.get("speaking_latency_ms", 800.0)
                    
                    diagnostics.record_wake_success(score=wake_score, latency_ms=wake_latency_ms)
                    diagnostics.record_audio_quality(quality_metrics)
                    diagnostics.record_noise_sample(quality_metrics["background_noise"])

                    try:
                        state.working_memory.set("wake_word_activation", True)
                        state.working_memory.set("listening_state", "listening")
                        state.working_memory.set("recognition_confidence", fused_score)
                        speaker_status = "verified" if (speaker_score is not None and verifier is not None and speaker_score >= verifier._threshold) else "unknown"
                        state.working_memory.set("current_speaker", speaker_status)
                        try:
                            state.working_memory.history_manager.add_entry(
                                "voice_event",
                                f"Wake word detected (confidence: {fused_score:.2f})",
                                {"confidence": fused_score, "speaker": speaker_status}
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        logger.debug(f"Failed to update working memory after wake: {e}")

                if enable_debug:
                    print_success("Wake Detected")
                if confirmation_sound:
                    play_confirmation_sound()
                    time.sleep(0.15)

                try:
                    with voice_config.stream_lock:
                        if stream.read_available > 0:
                            stream.read(stream.read_available)
                except Exception:
                    pass
            except Exception as wake_err:
                logger.error(f"Exception in wake processing: {wake_err}")
                try:
                    diagnostics.record_missed_wake(wake_score=wake_score, noise_floor=noise_floor)
                except Exception:
                    pass
                transition_to(VoiceState.VOICE_IDLE)
                save_state()
                return "continue"
        else:
            transition_to(VoiceState.PUSH_TO_TALK)
            try:
                state.working_memory.set("listening_state", "listening")
                state.working_memory.set("recognition_confidence", 1.0)
                state.working_memory.set("current_speaker", "verified")
                try:
                    state.working_memory.history_manager.add_entry("voice_event", "Push-to-Talk activation triggered")
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Failed to set PTT memory properties: {e}")
            try:
                input("Press ENTER to record a command...")
            except KeyboardInterrupt:
                save_state()
                return "break"
            except EOFError:
                logger.debug("PTT: No TTY detected — daemon mode, shortcut is the trigger.")
                if _first_ptt_since_activation:
                    _first_ptt_since_activation = False
                else:
                    while not shutdown_event.is_set() and _current_state not in (VoiceState.INACTIVE, VoiceState.TEXT_MODE):
                        if voice_active_event.is_set():
                            voice_active_event.clear()
                            break
                        time.sleep(0.1)
                    else:
                        save_state()
                        return "break"
    else:
        skip_idle_wait = False

    transition_to(VoiceState.LISTENING)
    if last_printed_state != VoiceState.LISTENING:
        print_info("🎤 Listening...")
        last_printed_state = VoiceState.LISTENING
        
    try:
        from nova.dashboard.event_bus import emit
        emit("speech_started", module="voice", status="running")
    except Exception:
        pass
        
    cmd_start   = time.time()
    record_start = time.time()
    muted = False
    try:
        subprocess.run(
            ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        muted = True
    except Exception:
        pass

    command_wav = None
    try:
        command_wav = record_audio_from_stream(
            stream, calibrated_threshold=speech_threshold,
            hp_filter=hp_filter, rnnoise=rnnoise, agc=agc, vad=vad, aec=aec
        )
    except Exception as e:
        print_error(f"Recording failed: {e}")
    finally:
        if muted:
            try:
                subprocess.run(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    if command_wav is None:
        try:
            from nova.dashboard.event_bus import emit
            emit("speech_finished", module="voice", status="failed", metadata={"reason": "recording_failed"})
        except Exception:
            pass
        save_state()
        return "continue"

    record_dur = time.time() - record_start
    try:
        from nova.dashboard.event_bus import emit
        emit("speech_finished", module="voice", status="success", metadata={"duration": record_dur})
    except Exception:
        pass

    if isinstance(command_wav, bytes):
        try:
            with wave.open(io.BytesIO(command_wav), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            diag = AudioDiagnostics(SAMPLE_RATE)
            m = diag.measure(samples)
            last_command_snr = m.get('snr_db', None)
            last_clipping_pct = m.get('clipping_pct', None)
        except Exception as diag_err:
            logger.debug(f"Diagnostics measurement failed: {diag_err}")

    transition_to(VoiceState.TRANSCRIBING)
    if enable_debug:
        print_info("🧠 Transcribing")
    try:
        from nova.dashboard.event_bus import emit
        emit("transcription_partial", module="stt", status="running")
    except Exception:
        pass

    t0 = time.time()
    try:
        text = stt_provider.transcribe(command_wav, silent=True)
        sm._stt_healthy = True
    except Exception as e:
        print_error(f"Transcription failed: {e}")
        try:
            from nova.dashboard.event_bus import emit
            emit("transcription_complete", module="stt", status="failed", metadata={"error": str(e)})
        except Exception:
            pass

        logger.warning(f"STT failed: {e}. Re-initializing STT provider...")
        try:
            stt_provider = get_stt_provider()
            sm._stt_healthy = True
        except Exception as stt_err:
            logger.error(f"Failed to re-initialize STT provider: {stt_err}")
            sm._stt_healthy = False
        save_state()
        return "continue"
    transcribe_dur = time.time() - t0

    if not text:
        print_warning("I didn't catch that.")
        last_printed_state = VoiceState.VOICE_IDLE
        save_state()
        return "continue"

    print_success(f'Heard: "{text}"')
    try:
        state.working_memory.set("final_transcription", text)
        try:
            state.working_memory.history_manager.add_entry(
                "voice_event",
                f"Speech transcribed: '{text}'",
                {"transcription": text}
            )
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"Failed to set final_transcription: {e}")

    if text.lower().strip().rstrip(".") in ("exit", "quit", "goodbye"):
        transition_to(VoiceState.SPEAKING)
        assistant_reply = "Goodbye!"
        speak(assistant_reply)
        try:
            update_working_memory_after_turn(
                working_memory=state.working_memory,
                user_message=text,
                assistant_reply=assistant_reply,
                intent="exit",
                topic="session_end"
            )
        except Exception as wm_err:
            logger.debug(f"Failed to update working memory: {wm_err}")
        save_state()
        return "break"

    if _is_interrupt_phrase(text):
        print_info("🛑 Stop command heard — going back to listening.")
        transition_to(VoiceState.SPEAKING)
        assistant_reply = "Sure, I'm listening."
        speak(assistant_reply)
        try:
            update_working_memory_after_turn(
                working_memory=state.working_memory,
                user_message=text,
                assistant_reply=assistant_reply,
                intent="stop",
                topic="conversation_control"
            )
        except Exception as wm_err:
            logger.debug(f"Failed to update working memory: {wm_err}")
        last_printed_state = VoiceState.VOICE_IDLE
        if confirmation_sound:
            play_confirmation_sound()
        skip_idle_wait = True
        save_state()
        return "continue"

    transition_to(VoiceState.EXECUTING)
    if last_printed_state != VoiceState.EXECUTING:
        print_info("▶ Executing...")
        last_printed_state = VoiceState.EXECUTING

    from nova.core.executor import CommandExecutor
    CommandExecutor.clear_last_commands()

    from nova.spelling import correct_query_spelling, correct_action_data
    import nova.spelling as spelling
    corrected = correct_query_spelling(text)

    try:
        from nova.dashboard.event_bus import emit
        emit("transcription_complete", module="stt", status="success", metadata={"raw_text": text, "corrected_text": corrected})
    except Exception:
        pass

    requires_confirm = False
    confirm_prompt = ""
    if hasattr(stt_provider, "last_avg_logprob") and stt_provider.last_avg_logprob < -0.85:
        requires_confirm = True
        confirm_prompt = f"Did you mean '{corrected}'?"
    if spelling.last_correction_applied:
        try:
            from nova.dashboard.event_bus import emit
            emit("memory_indexed", module="memory", status="success", metadata={
                "action": "spelling_correction",
                "raw_query": text,
                "corrected_query": corrected,
                "prompt": spelling.correction_prompt
            })
        except Exception:
            pass
        requires_confirm = True
        confirm_prompt = spelling.correction_prompt

    if requires_confirm and confirm_prompt:
        confirmed = get_user_confirmation(confirm_prompt, stream, speech_threshold)
        if not confirmed:
            assistant_reply = "Cancelled."
            speak(assistant_reply)
            try:
                update_working_memory_after_turn(
                    working_memory=state.working_memory,
                    user_message=text,
                    assistant_reply=assistant_reply,
                    intent="confirm_cancel",
                    topic="confirmation"
                )
            except Exception as wm_err:
                logger.debug(f"Failed to update working memory: {wm_err}")
            last_printed_state = VoiceState.VOICE_IDLE
            save_state()
            return "continue"

    try:
        from nova.dashboard.event_bus import emit
        emit("llm_started", module="llm", status="running", metadata={"query": corrected})
    except Exception:
        pass

    try:
        raw_response = ai_client.parse_intent(corrected)
        try:
            from nova.dashboard.event_bus import emit
            emit("llm_finished", module="llm", status="success", metadata={"query": corrected, "response": raw_response})
        except Exception:
            pass
    except Exception as e:
        print_error(f"Intent parsing failed: {e}")
        try:
            from nova.dashboard.event_bus import emit
            emit("llm_finished", module="llm", status="failed", metadata={"query": corrected, "error": str(e)})
        except Exception:
            pass
        save_state()
        return "continue"

    if not raw_response:
        print_error("All AI APIs failed. Check your API keys and network.")
        save_state()
        return "continue"

    from nova.parser import parse_and_validate_action
    try:
        actions = parse_and_validate_action(raw_response)
    except Exception as e:
        print_error(f"Action validation failed: {e}")
        save_state()
        return "continue"

    if not actions:
        print_error("Could not parse an action from the AI response.")
        save_state()
        return "continue"

    success_msgs = []
    is_long, ack_text, success_text, fail_text = check_long_running_action(dispatcher, actions, text)
    
    ack_thread = None
    if is_long:
        ack_thread = threading.Thread(target=speak, args=(ack_text,))
        ack_thread.start()

    _stop_background_interrupt_listener()
    if stt_provider is not None and stream is not None:
        _start_background_interrupt_listener(stream, stt_provider, speech_threshold)

    from nova.ai.planner import Goal
    from nova.ai.reasoning import route_query_to_planner_pipeline
    from nova.core.state import StateManager
    
    approval_required = not StateManager.is_autonomous()
    goal = Goal(description=corrected)
    goal.metadata = {"actions": actions}
    
    try:
        result_message = route_query_to_planner_pipeline(
            query=corrected,
            working_memory=state.working_memory,
            dispatcher=dispatcher,
            approval_required=approval_required,
            actions=actions
        )
        if "error" in result_message.lower() or "failed" in result_message.lower():
            print_error(result_message)
        else:
            print_success(result_message)
            success_msgs.append(result_message)
    except Exception as e:
        print_error(f"Plan execution failed: {e}")

    if verifier is not None:
        verifier.commit_adaptation()

    total_dur = time.time() - cmd_start
    logger.info(f"Record: {record_dur:.2f}s | Transcribe: {transcribe_dur:.2f}s | Total: {total_dur:.2f}s")

    if ack_thread:
        ack_thread.join(timeout=2.0)

    _turn_tts_ms = 0.0
    if is_long:
        if success_msgs:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            assistant_reply = success_text
            _tts_start = time.perf_counter()
            speak(success_text)
            _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
        else:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            assistant_reply = fail_text
            _tts_start = time.perf_counter()
            speak(fail_text)
            _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
    else:
        if success_msgs:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            spoken = " ".join(clean_ansi(m) for m in success_msgs)
            user_text_lower = text.lower()
            read_full_phrases = [
                "read everything", "read the full response", "read the complete response", 
                "read full response", "read all", "read full text", "read the full text"
            ]
            read_full = any(phrase in user_text_lower for phrase in read_full_phrases)
            
            if read_full:
                assistant_reply = spoken
                _tts_start = time.perf_counter()
                speak(spoken)
                _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
            else:
                try:
                    spoken_summary = ai_client.generate_tts_summary(text, spoken)
                except Exception as e:
                    logger.debug(f"Failed to generate spoken summary: {e}")
                    spoken_summary = spoken
                assistant_reply = spoken_summary
                _tts_start = time.perf_counter()
                speak(spoken_summary)
                _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0

    if enable_debug:
        print_success("✔ Finished")

    try:
        _turn_e2e_ms = (time.time() - cmd_start) * 1000.0
        _turn_stt_ms = transcribe_dur * 1000.0
        _turn_quality = quality_metrics.get("overall_quality", 1.0) if quality_metrics is not None else 1.0
        _turn_noise   = quality_metrics.get("background_noise", 0.0) if quality_metrics is not None else 0.0
        _turn_speaker = float(speaker_score) if speaker_score is not None else None
        diagnostics.record_turn(
            latency_ms=_turn_e2e_ms,
            stt_latency_ms=_turn_stt_ms,
            tts_latency_ms=_turn_tts_ms,
            audio_quality=_turn_quality,
            speaker_confidence=_turn_speaker,
            noise_floor=_turn_noise,
        )
    except Exception as _diag_err:
        logger.debug(f"Diagnostics record_turn failed: {_diag_err}")

    try:
        intent = actions[0].get("action") if actions else None
        topic = infer_topic(intent, corrected, actions)
        update_working_memory_after_turn(
            working_memory=state.working_memory,
            user_message=text,
            assistant_reply=assistant_reply,
            intent=intent,
            topic=topic
        )
    except Exception as wm_err:
        logger.debug(f"Failed to update working memory: {wm_err}")

    _stop_background_interrupt_listener()

    if voice_config.interrupt_speaking:
        voice_config.interrupt_speaking = False
        print_success("Nova interrupted. Listening...")
        if confirmation_sound:
            play_confirmation_sound()
        skip_idle_wait = True
        save_state()
        return "continue"

    try:
        time.sleep(0.8)
        if stream is not None:
            with voice_config.stream_lock:
                if stream.read_available > 0:
                    stream.read(stream.read_available)
    except Exception:
        pass

    if sm._deferred_deactivate:
        sm._deferred_deactivate = False
        print_info("Nova has stopped listening.")
        transition_to(VoiceState.INACTIVE)

    save_state()
    return "continue"


def run_voice_loop(ai_client, dispatcher, interactive=False, working_memory=None) -> str:
    state = VoiceLoopState(working_memory=working_memory)
    try:
        state.working_memory.set("voice_session_state", "active")
        try:
            state.working_memory.history_manager.add_entry("voice_event", "Voice session started")
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"Failed to set voice_session_state: {e}")

    try:
        from nova.browser.manager import BrowserManager
        BrowserManager._working_memory = state.working_memory
    except Exception as e:
        logger.debug(f"Failed to inject working memory to BrowserManager: {e}")

    if dispatcher:
        for action in dispatcher.values():
            try:
                action.working_memory = state.working_memory
            except Exception:
                pass

    def transition_to(new_state: VoiceState, detail: str = ""):
        state.current_state = new_state
        sm._current_state = new_state
        logger.debug(f"[STATE] Transitioned to {new_state.name}{f' ({detail})' if detail else ''}")
        try:
            from nova.dashboard.event_bus import emit
            emit("voice_state_change", module="voice", status="running", metadata={"state": new_state.name, "detail": detail})
        except Exception:
            pass

    if interactive:
        transition_to(VoiceState.VOICE_IDLE)
    else:
        transition_to(VoiceState.INACTIVE)
    print_success("Voice Mode Ready")

    try:
        while True:
            if shutdown_event.is_set():
                break
            action = process_single_iteration(state, ai_client, dispatcher, transition_to)
            if action == "break":
                break
            elif action == "continue":
                continue
            elif action in ("menu", "exit"):
                return action
    except KeyboardInterrupt:
        print()

    transition_to(VoiceState.SHUTDOWN)
    sm._mic_healthy = False

    try:
        state.diagnostics.flush_to_disk()
    except Exception:
        pass

    if state.stream is not None:
        try:
            state.stream.stop()
            state.stream.close()
        except Exception:
            pass
        voice_config.active_stream = None

    if state.rnnoise:
        try:
            state.rnnoise.destroy()
        except Exception:
            pass

    if state.aec:
        try:
            state.aec.destroy()
        except Exception:
            pass

    print_info("Voice Mode Closed")
    try:
        state.working_memory.set("voice_session_state", "inactive")
        state.working_memory.set("listening_state", "idle")
        try:
            state.working_memory.history_manager.add_entry("voice_event", "Voice session stopped")
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"Failed to reset voice properties: {e}")
    return "menu"




