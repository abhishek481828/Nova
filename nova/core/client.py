import sys
import os
import json
import socket
from nova.utils import print_error, resolve_chromium_bin

def run_client(query: str) -> None:
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(("127.0.0.1", 11435))
    except Exception:
        print_error("Failed to connect to Nova daemon. Is it running? Start it with: nova start")
        sys.exit(1)
        
    resolved_chromium = resolve_chromium_bin()

    payload = {
        "query": query,
        "env": dict(os.environ),
        "chromium_bin": resolved_chromium,
        "chrome_bin": resolved_chromium
    }
    message = f"NOVA_JSON:{json.dumps(payload)}"
    client.sendall(message.encode("utf-8"))
    
    while True:
        try:
            data = client.recv(4096)
            if not data:
                break
            text = data.decode("utf-8")
            
            # Format status response if received
            if text.startswith('{"running":'):
                try:
                    status = json.loads(text)
                    print(f"● Nova Assistant Service")
                    print(f"   Background Service Health: {status['health']}")
                    print(f"   Current State:             {status['state']}")
                    print(f"   Microphone:                {status['microphone']}")
                    print(f"   Wake-Word Engine:          {status['wake_word']}")
                    print(f"   Whisper (STT):             {status['whisper']}")
                    print(f"   ElevenLabs (TTS):          {status['elevenlabs']}")
                    print(f"   Browser Automation:        {status['browser']}")
                except Exception:
                    pass
                break
            
            # Check if prompt requires a y/n confirmation
            if "(y/n):" in text:
                choice = input(text)
                client.sendall(choice.encode("utf-8"))
            else:
                sys.stdout.write(text)
                sys.stdout.flush()
        except KeyboardInterrupt:
            print()
            break
    client.close()
