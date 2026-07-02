import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from nova.voice.tts import ElevenLabsProvider
    _TTS_AVAILABLE = True
except ImportError:
    ElevenLabsProvider = None  # type: ignore
    _TTS_AVAILABLE = False


def run_test():
    print("=== Speak Debug Test ===")
    provider = ElevenLabsProvider()
    
    print(f"API Key present: {provider.api_key is not None}")
    print(f"Voice ID: {provider.voice_id}")
    
    text = "Hello Abhishek, I am Nova."
    print(f"\nCalling provider.speak('{text}')...")
    
    import tempfile
    from elevenlabs.client import ElevenLabs
    from nova.voice.config import TEMP_AUDIO_DIR
    
    mp3_path = None
    try:
        client = ElevenLabs(api_key=provider.api_key)
        
        # 1. Try custom voice ID
        try:
            print("Step 1: synthesis with custom voice...")
            audio = client.text_to_speech.convert(
                text=text,
                voice_id=provider.voice_id,
                model_id="eleven_turbo_v2_5",
                output_format="mp3_44100_128",
            )
            # Try parsing a chunk to trigger network request
            chunks = list(audio)
            print(f"Step 1 succeeded. Got {len(chunks)} chunks.")
        except Exception as e1:
            print(f"Step 1 failed: {e1}")
            if provider.voice_id != "EXAVITQu4vr4xnSDxMaL":
                print("Step 2: synthesis with default Bella voice...")
                audio = client.text_to_speech.convert(
                    text=text,
                    voice_id="EXAVITQu4vr4xnSDxMaL",
                    model_id="eleven_turbo_v2_5",
                    output_format="mp3_44100_128",
                )
                chunks = list(audio)
                print(f"Step 2 succeeded. Got {len(chunks)} chunks.")
            else:
                raise e1
        
        # 2. Write to temp file
        print("Writing to file...")
        temp_fd, mp3_path = tempfile.mkstemp(suffix=".mp3", dir=TEMP_AUDIO_DIR)
        os.close(temp_fd)
        
        with open(mp3_path, "wb") as f:
            for chunk in chunks:
                f.write(chunk)
                
        print(f"File size: {os.path.getsize(mp3_path)} bytes")
        print("Playing file...")
        provider.fallback._play(mp3_path)
        print("Playback complete.")
        
    except Exception as e:
        print(f"✗ Speak outer block failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if mp3_path and os.path.exists(mp3_path):
            os.remove(mp3_path)

if __name__ == "__main__":
    run_test()
