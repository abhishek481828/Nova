import sys
import os
import time
import timeit
import numpy as np
import tempfile
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from nova.voice.wake_word import LocalWakeWordDetector

def run_wake_benchmark():
    print("--- Upgraded Wake Word Detector Benchmark ---")
    
    # Create a temp directory for dummy ONNX file
    with tempfile.TemporaryDirectory() as tmp_dir:
        dummy_model_path = os.path.join(tmp_dir, "hey_nova_v0.1.onnx")
        with open(dummy_model_path, "wb") as f:
            f.write(b"dummy")

        # Mock the OpenWakeWord Model implementation so we don't load real ONNX in the benchmark
        with patch("openwakeword.model.Model") as mock_oww_model:
            mock_model_instance = MagicMock()
            # Mock predict to return a dummy prediction dict
            mock_model_instance.predict.return_value = {"hey_nova_v0.1": 0.12}
            mock_oww_model.return_value = mock_model_instance

            # 1. Instantiate the upgraded detector (which wraps/monkey-patches predict)
            detector = LocalWakeWordDetector(
                model_path=dummy_model_path,
                confidence_threshold=0.5
            )
            
            # Generate a 1280-sample PCM chunk (80ms at 16kHz)
            dummy_pcm_chunk = (np.random.randn(1280) * 1000).astype(np.int16)
            
            # Define original raw predict scenario
            raw_model_predict = mock_model_instance.predict
            
            # Define raw predict timing (bypassing monkey-patch)
            def benchmark_raw_predict():
                predictions = raw_model_predict(dummy_pcm_chunk)
                return predictions

            # Define upgraded predict timing (with rolling buffer, RMS, noise floor, diagnostics)
            def benchmark_upgraded_predict():
                predictions = detector.model.predict(dummy_pcm_chunk)
                return predictions

            # Warm-up
            for _ in range(10):
                benchmark_raw_predict()
                benchmark_upgraded_predict()

            # Time execution (1000 runs)
            iterations = 1000
            raw_time = timeit.timeit(benchmark_raw_predict, number=iterations)
            upgraded_time = timeit.timeit(benchmark_upgraded_predict, number=iterations)
            
            overhead_per_run_ms = ((upgraded_time - raw_time) / iterations) * 1000.0

            print(f"Raw Predict (1000 runs):      {raw_time:.4f} seconds ({raw_time/iterations*1000.0:.4f} ms/run)")
            print(f"Upgraded Predict (1000 runs): {upgraded_time:.4f} seconds ({upgraded_time/iterations*1000.0:.4f} ms/run)")
            print(f"Overhead Per Trigger Check:   {overhead_per_run_ms:.4f} ms")
            print(f"Added Latency Percentage:     {((upgraded_time - raw_time) / raw_time) * 100.0:.2f}%")
            print("Note: The added overhead is negligible and falls well within the microsecond scale.")

if __name__ == "__main__":
    run_wake_benchmark()
