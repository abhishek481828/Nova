#!/usr/bin/env python3
"""Quick command-line tool to turn phone microphone ON or OFF."""

import sys
from nova.actions.audio_voice import AudioCaptureStartAction, AudioCaptureStopAction

def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "on"
    if cmd in ("on", "open", "start"):
        res = AudioCaptureStartAction().execute({})
        print(f"🎙️  {res}")
    elif cmd in ("off", "close", "stop"):
        res = AudioCaptureStopAction().execute({})
        print(f"🔇 {res}")
    else:
        print("Usage: python nova/mic.py [on|off]")

if __name__ == "__main__":
    main()
