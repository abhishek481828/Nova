import sys
import os
import time
import timeit
import numpy as np
import io
import wave
import tempfile

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from nova.voice.audio_processor import RNNoiseWrapper
from nova.voice.stt import WhisperSTTProvider

def run_rnnoise_benchmark():
    print("--- RNNoise Processing Benchmark ---")
    rnnoise = RNNoiseWrapper()
    if not rnnoise.is_available():
        print("RNNoise shared library is not available. Skipping RNNoise benchmark.")
        return

    # Generate dummy float32 audio chunk (480 samples = 30ms at 16kHz)
    dummy_chunk = np.random.randn(480).astype(np.float32) * 0.05
    
    # Define old subframe method
    def old_subframe_method():
        sub_frames = np.split(dummy_chunk, 3)
        denoised_subs = [rnnoise.denoise_frame(sf) for sf in sub_frames]
        result = np.concatenate(denoised_subs)
        return result

    # Define new bulk method
    def new_bulk_method():
        result = rnnoise.denoise_chunk(dummy_chunk)
        return result

    # Warm-up
    for _ in range(5):
        old_subframe_method()
        new_bulk_method()

    # Time execution
    iterations = 200
    old_time = timeit.timeit(old_subframe_method, number=iterations)
    new_time = timeit.timeit(new_bulk_method, number=iterations)

    print(f"Old Subframe Method (200 runs): {old_time:.4f} seconds ({old_time/iterations*1000:.2f} ms/run)")
    print(f"New Bulk Method (200 runs):     {new_time:.4f} seconds ({new_time/iterations*1000:.2f} ms/run)")
    print(f"RNNoise Speedup:                {old_time / new_time:.2f}x")
    
    rnnoise.destroy()

def run_stt_benchmark():
    print("\n--- Whisper STT Decoding & I/O Benchmark ---")
    # Generate dummy WAV bytes in memory
    dummy_wav_io = io.BytesIO()
    with wave.open(dummy_wav_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        # 1 second of dummy signal
        dummy_int16 = (np.random.randn(16000) * 1000).astype(np.int16)
        wf.writeframes(dummy_int16.tobytes())
    dummy_wav_bytes = dummy_wav_io.getvalue()

    # Define old disk write method
    def old_disk_write_method():
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(dummy_wav_bytes)
        tmp.close()
        audio_path = tmp.name
        
        # Read back
        with wave.open(audio_path, 'rb') as wf:
            raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Cleanup
        os.unlink(audio_path)
        return samples

    # Define new in-memory method
    def new_in_memory_method():
        with wave.open(io.BytesIO(dummy_wav_bytes), 'rb') as wf:
            raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return samples

    # Warm-up
    for _ in range(5):
        old_disk_write_method()
        new_in_memory_method()

    # Time execution
    iterations = 500
    old_time = timeit.timeit(old_disk_write_method, number=iterations)
    new_time = timeit.timeit(new_in_memory_method, number=iterations)

    print(f"Old Disk I/O Method (500 runs):  {old_time:.4f} seconds ({old_time/iterations*1000:.4f} ms/run)")
    print(f"New In-Memory Method (500 runs): {new_time:.4f} seconds ({new_time/iterations*1000:.4f} ms/run)")
    print(f"STT Decoding Speedup:            {old_time / new_time:.2f}x")

if __name__ == "__main__":
    run_rnnoise_benchmark()
    run_stt_benchmark()
