import os
import sys
import time
import numpy as np
import sounddevice as sd

# Include project root
try:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
except Exception:
    pass

from nova.logger import logger
from nova.voice.config import (
    SAMPLE_RATE, CHANNELS, enable_wake_word, wake_word_model_path,
    wake_word_threshold, confirmation_sound, VAD_THRESHOLD, NOISE_FLOOR_MARGIN
)
from nova.voice.speaker import SpeakerVerifier
from nova.voice.whisper import get_stt_provider
from nova.voice.tts import speak
from nova.voice.wakeword import LocalWakeWordDetector
from nova.voice.pipeline.processors import WebRTCVoiceActivityDetector
from nova.voice.pipeline.core import play_confirmation_sound, record_audio_from_stream, clean_ansi
from nova.utils import print_info, print_success, print_warning, print_error

def run_voice_loop(ai_client, dispatcher) -> str:
    """
    Runs the Voice Mode interaction loop in a production-quality architecture.
    Uses a single shared InputStream throughout the session.
    """
    # Initialize STT Provider
    stt_provider = get_stt_provider()
    
    # Import optional libraries lazily
    from nova.voice.pipeline.processors import AmbientCalibrator
    
    # Check input device availability and specs
    try:
        device_info = sd.query_devices(kind='input')
        if not device_info:
            raise RuntimeError("No input microphone device found.")
    except Exception as e:
        print_error("Microphone unavailable or not detected.")
        print_info(f"Error details: {e}")
        return "menu"
        
    # Open shared input stream once for the entire Voice Mode session
    try:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='float32')
        stream.start()
    except Exception as e:
        logger.debug(f"Failed to open audio input stream: {e}")
        print_error(f"Microphone unavailable. Failed to open stream at {SAMPLE_RATE}Hz, mono, float32.")
        print_info(f"Error details: {e}")
        return "menu"
        
    # Run dynamic microphone calibration using the shared stream
    print_info("🔇 Calibrating microphone...")
    try:
        calib_samples = int(SAMPLE_RATE * 1.5)
        calib_recording, overflow = stream.read(calib_samples)
        
        calibrator = AmbientCalibrator()
        calibrator.calibrate(calib_recording)
        noise_floor = calibrator.noise_floor
        speech_threshold = calibrator.speech_threshold
        print_info(f"Noise floor: {noise_floor:.5f} | Speech threshold: {speech_threshold:.5f}")
    except Exception as e:
        logger.debug(f"Calibration failed: {e}")
        noise_floor = VAD_THRESHOLD
        speech_threshold = VAD_THRESHOLD + NOISE_FLOOR_MARGIN
        print_warning(f"Calibration failed, falling back to default threshold: {speech_threshold:.5f}")
        
    # Sanity-clamp: if noise floor > 0.5 the mic is saturated/always-loud.
    if noise_floor > 0.5:
        print_warning(f"High noise floor ({noise_floor:.3f}) detected — using WebRTC VAD only.")
        speech_threshold = 0.02
        
    # Try to instantiate OpenWakeWord Detector
    wake_detector = None
    use_wake_word = enable_wake_word
    
    if use_wake_word:
        try:
            wake_detector = LocalWakeWordDetector(
                model_path=wake_word_model_path,
                confidence_threshold=wake_word_threshold
            )
            print_success("👂 Wake-word engine ready")
        except Exception as e:
            print_error("Hey Nova wake-word model not found.")
            print_info(f"Attempted model path: {wake_word_model_path}")
            logger.debug(f"Wake word initialization error: {e}")
            use_wake_word = False
            print_warning("Continuing in Push-to-Talk mode.")
            
    _last_trigger_time = 0.0  # cooldown tracker
    WAKE_COOLDOWN = 1.5       # seconds to ignore wake-word after a successful trigger
    
    try:
        while True:
            try:
                # ==========================================
                # 1. IDLE MODE (Wake-word detection)
                # ==========================================
                if use_wake_word:
                    print_info("👂 Waiting for wake phrase")
                    
                    # Flush stream buffer before entering passive listen to avoid stale audio trigger
                    if stream.read_available > 0:
                        stream.read(stream.read_available)
                        
                    audio_accumulator = np.array([], dtype=np.float32)
                    wake_word_triggered = False
                    
                    while not wake_word_triggered:
                        try:
                            # Read smaller chunks to minimize latency
                            recording, overflow = stream.read(480) # 30ms block size
                        except Exception as e:
                            logger.debug(f"Audio stream read error during passive listen: {e}")
                            time.sleep(0.01)
                            continue
                            
                        # Append to buffer accumulator (ring buffer)
                        audio_accumulator = np.concatenate([audio_accumulator, recording.flatten()])
                        
                        # Extract exactly 1280 samples for OpenWakeWord inference
                        while len(audio_accumulator) >= 1280:
                            chunk = audio_accumulator[:1280]
                            audio_accumulator = audio_accumulator[1280:] # Shift buffer
                            
                            # Noise-aware normalization
                            chunk_rms = float(np.sqrt(np.mean(chunk ** 2)))
                            NOISE_GATE_RATIO = 2.0
                            if chunk_rms > noise_floor * NOISE_GATE_RATIO and chunk_rms > 1e-6:
                                target_rms = 0.08
                                chunk_norm = chunk * (target_rms / chunk_rms)
                            else:
                                chunk_norm = chunk
                            
                            pcm_chunk = (np.clip(chunk_norm, -1.0, 1.0) * 32767).astype(np.int16)
                            
                            predictions = wake_detector.model.predict(pcm_chunk)
                            score = predictions.get(wake_detector.model_name, 0.0)
                            
                            if score >= wake_word_threshold:
                                now = time.time()
                                if now - _last_trigger_time < WAKE_COOLDOWN:
                                    continue
                                _last_trigger_time = now
                                wake_word_triggered = True
                                break
                                
                        time.sleep(0.01)
                        
                    print_success("🔔 Wake phrase detected")
                    
                    # Play confirmation and clear stream buffer
                    if confirmation_sound:
                        play_confirmation_sound()
                        time.sleep(0.2)  # wait for chime to finish
                        if stream.read_available > 0:
                            stream.read(stream.read_available)
                else:
                    # Push-to-Talk Mode fallback
                    try:
                        input("🎤 Press Enter to start recording command...")
                    except (KeyboardInterrupt, EOFError):
                        print()
                        print_info("Exiting Voice Mode.")
                        return "menu"
                
                # ==========================================
                # 2. COMMAND MODE (Recording & Processing)
                # ==========================================
                print_info("🎤 Listening")
                command_start_time = time.time()
                record_start = time.time()
                
                # Temporarily mute system audio to ensure clean microphone capture
                muted = False
                try:
                    subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    muted = True
                except Exception:
                    pass
                
                try:
                    command_wav_bytes = record_audio_from_stream(stream, calibrated_threshold=speech_threshold)
                except Exception as e:
                    print_error(f"Recording command failed.")
                    print_info(f"Error details: {e}")
                    continue
                finally:
                    if muted:
                        try:
                            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        except Exception:
                            pass
                            
                record_duration = time.time() - record_start
                
                # Transcribe command
                print_info("🧠 Transcribing")
                upload_start = time.time()
                try:
                    text = stt_provider.transcribe(command_wav_bytes, silent=True)
                except Exception as e:
                    print_error(f"STT transcription failed: {e}")
                    continue
                    
                upload_duration = time.time() - upload_start
                
                if not text:
                    print_warning("Could not recognize speech — please try again.")
                    continue
                    
                print_success(f"Heard: \"{text}\"")
                
                # Check for exit commands
                if text.lower().strip().rstrip(".") in ("exit", "quit", "goodbye"):
                    speak("Goodbye!")
                    print_info("Goodbye!")
                    return "exit"
                    
                # Process recognized text
                print_info(f"▶ Executing")
                
                # Reset executor history for the turn
                from nova.core.executor import CommandExecutor
                CommandExecutor.clear_last_commands()
                
                # Correct spelling
                from nova.spelling import correct_query_spelling, correct_action_data
                corrected_text = correct_query_spelling(text)
                
                # Run intent parser
                try:
                    raw_response = ai_client.parse_intent(corrected_text)
                except Exception as e:
                    print_error(f"Intent parsing exception occurred: {e}")
                    continue
                    
                if not raw_response:
                    print_error("Failed to connect to Ollama or parse the request. Please check if Ollama is running.")
                    continue
                    
                from nova.parser import parse_and_validate_action
                try:
                    actions_list = parse_and_validate_action(raw_response)
                except Exception as e:
                    print_error(f"Action validation exception occurred: {e}")
                    continue
                    
                if not actions_list:
                    print_error("Could not determine or parse action intent from AI response.")
                    continue
                    
                # Execute the actions
                success_messages = []
                for action_data in actions_list:
                    action_data = correct_action_data(action_data, corrected_text)
                    action_name = action_data.get("action")
                    action_handler = dispatcher.get(action_name)
                    
                    if not action_handler:
                        print_error(f"Intent recognized as '{action_name}', but no action handler is registered.")
                        continue
                        
                    print_info(f"Action parsed: {action_name}")
                    try:
                        result_message = action_handler.execute(action_data)
                    except Exception as e:
                        print_error(f"Action executor exception occurred during execution of '{action_name}': {e}")
                        continue
                        
                    if "error" in result_message.lower() or "failed" in result_message.lower():
                        print_error(result_message)
                    elif "aborted" in result_message.lower() or "cancelled" in result_message.lower():
                        print_warning(result_message)
                    else:
                        print_success(result_message)
                        success_messages.append(result_message)
                        
                total_response_time = time.time() - command_start_time
                logger.info(f"Metrics - Record: {record_duration:.2f}s | Upload/Transcribe: {upload_duration:.2f}s | Total Response Time: {total_response_time:.2f}s")
                
                # Speak confirmation if actions succeeded
                if success_messages:
                    spoken_text = " ".join([clean_ansi(msg) for msg in success_messages])
                    print_info(f"🔊 Speaking: {spoken_text}")
                    speak(spoken_text)
                    
                print_success("✔ Finished")
                
                # Flush mic buffer before next Idle Mode cycle starts
                try:
                    if stream.read_available > 0:
                        stream.read(stream.read_available)
                except Exception:
                    pass
                _last_trigger_time = time.time()
                
            except KeyboardInterrupt:
                print()
                print_info("Exiting Voice Mode.")
                return "menu"
            except Exception as e:
                logger.debug(f"Unexpected error in voice loop: {e}")
                print_error(f"An unexpected error occurred: {e}")
                time.sleep(0.5)
                continue
    finally:
        # Clean up input stream on function exit
        if 'stream' in locals():
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
