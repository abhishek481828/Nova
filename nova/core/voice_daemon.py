"""Continuous Background Voice Daemon for Nova Assistant.

Listens for voice commands from paired phone companion devices continuously and executes actions.
"""

import time
import sys
import logging
from nova.actions.phone_control import send_companion_command
from nova.companion.audio_receiver import global_audio_receiver
from nova.voice.whisper import get_stt_provider
from nova.actions.audio_voice import pcm_to_wav
from nova.ai.ollama import OllamaClient
from nova.parser import parse_and_validate_action
from nova.actions import get_action_dispatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nova.voice_daemon")

def run_voice_daemon():
    logger.info("==================================================")
    logger.info("🎙️ NOVA CONTINUOUS BACKGROUND VOICE DAEMON ACTIVE")
    logger.info("==================================================")
    logger.info("Listening for phone microphone voice commands in background...")
    
    stt = get_stt_provider()
    client = OllamaClient()
    dispatcher = get_action_dispatcher()
    
    while True:
        try:
            pcm_bytes = global_audio_receiver.get_stt_audio_data()
            if pcm_bytes and len(pcm_bytes) >= 32000: # 1 second of audio
                wav_bytes = pcm_to_wav(pcm_bytes)
                text = stt.transcribe(wav_bytes, silent=True).strip()
                
                if text:
                    logger.info(f"🗣️ Heard from Phone Mic: \"{text}\"")
                    sentences = [s.strip() for s in text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
                    for sentence in sentences:
                        raw_intent = client.parse_intent(sentence)
                        if raw_intent:
                            actions = parse_and_validate_action(raw_intent)
                            if actions:
                                for act in actions:
                                    action_name = act.get("action")
                                    params = {k: v for k, v in act.items() if k != "action"}
                                    if action_name and action_name != "chat_response":
                                        handler = dispatcher.get(action_name)
                                        if handler:
                                            res = handler.execute(params)
                                            logger.info(f"▶ Executed '{sentence}': {res}")
                                        else:
                                            res = send_companion_command(action_name, params)
                                            logger.info(f"▶ Executed phone action '{action_name}': {res}")
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Voice daemon loop error: {e}")
            time.sleep(1.0)

if __name__ == "__main__":
    run_voice_daemon()
