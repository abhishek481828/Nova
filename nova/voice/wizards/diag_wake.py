#!/usr/bin/env python3
"""
Wake-word diagnostic: records 5 seconds, feeds audio to OpenWakeWord chunk-by-chunk
and prints scores. Say "Hey Nova" during the recording.
"""
import sys, os, glob
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
for venv_dir in glob.glob(os.path.join(project_root, ".venv/lib/python*/site-packages")):
    sys.path.append(venv_dir)

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import sounddevice as sd
from openwakeword.model import Model
import openwakeword

# Locate model
pkg = os.path.dirname(openwakeword.__file__)
model_path = os.path.join(pkg, "resources", "models", "hey_nova_v0.1.onnx")
model_name = "hey_nova_v0.1"
model = Model(wakeword_model_paths=[model_path])

SAMPLE_RATE = 16000
DURATION = 6  # seconds
CHUNK = 1280  # samples per inference window

print(f"🎙  Recording {DURATION}s — say 'Hey Nova' clearly now...")
recording = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype='float32')
sd.wait()
print("✅ Recording done. Running inference...\n")

flat = recording.flatten()
max_score = 0.0

for i in range(0, len(flat) - CHUNK, CHUNK // 2):   # 50% overlap for better detection
    chunk_f32 = flat[i:i + CHUNK]
    rms = float(np.sqrt(np.mean(chunk_f32 ** 2)))

    # Apply same normalization as conversation.py fix
    TARGET_RMS = 0.08
    if rms > 1e-6:
        chunk_norm = chunk_f32 * (TARGET_RMS / rms)
    else:
        chunk_norm = chunk_f32

    chunk_i16 = (np.clip(chunk_norm, -1.0, 1.0) * 32767).astype(np.int16)
    pred = model.predict(chunk_i16)
    score = pred.get(model_name, 0.0)

    t_ms = (i / SAMPLE_RATE) * 1000
    marker = " ◀ TRIGGERED" if score >= 0.5 else ""
    print(f"  t={t_ms:6.0f}ms  RMS={rms:.4f}  score={score:.4f}{marker}")
    if score > max_score:
        max_score = score

print(f"\nMax score reached: {max_score:.4f}")
if max_score >= 0.5:
    print("✅ Wake-word detection works!")
elif max_score >= 0.05:
    print(f"⚠️  Low scores — the threshold needs lowering (try 0.1 instead of 0.5)")
else:
    print("❌ Near-zero scores — audio format or model issue")
